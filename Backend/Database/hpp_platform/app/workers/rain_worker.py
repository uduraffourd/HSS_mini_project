from __future__ import annotations
from datetime import datetime, date, timedelta, timezone
from io import BytesIO
from typing import Iterable,List, Tuple
import pandas as pd
import requests
from sqlalchemy import insert
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import WeatherStation, Rainfall6Min
from app.db.session import SessionLocal
import os
import logging
logger = logging.getLogger(__name__)


APIKEY = os.getenv("METEOFRANCE_APIKEY")
URL_COMMANDE = "https://public-api.meteofrance.fr/public/DPClim/v1/commande-station/infrahoraire-6m"
URL_FICHIER  = "https://public-api.meteofrance.fr/public/DPClim/v1/commande/fichier"

HEADERS = {"Accept": "*/*", "apikey": APIKEY}


def _ensure_apikey():
    if not APIKEY:
        raise RuntimeError("METEOFRANCE_APIKEY is not set in environment")


# --- remplace TOUTE la fonction _call_commande par ceci ---

def _call_commande(station_code: str, start_iso: str, end_iso: str) -> str:
    params = {
        "id-station": station_code,
        "date-deb-periode": start_iso,
        "date-fin-periode": end_iso,
    }
    r = requests.get(URL_COMMANDE, headers=HEADERS, params=params, timeout=60)
    if r.status_code >= 400:
        # <<< ajout : message explicite
        raise RuntimeError(
            f"MF 6m commande failed ({r.status_code}). "
            f"Check station_code='{station_code}' (must be numeric, e.g. 70473001), "
            f"start='{start_iso}', end='{end_iso}'. "
            f"Response: {r.text[:400]}..."
        )
    j = r.json()

    cmde = None
    if isinstance(j, dict):
        # cas 1: {"return": "..."}
        if "return" in j and isinstance(j["return"], (str, int)):
            cmde = j["return"]
        # cas 2: {"elaboreProduitAvecDemandeResponse": {"return": "..."}}
        elif "elaboreProduitAvecDemandeResponse" in j and isinstance(j["elaboreProduitAvecDemandeResponse"], dict):
            inner = j["elaboreProduitAvecDemandeResponse"]
            if "return" in inner and isinstance(inner["return"], (str, int)):
                cmde = inner["return"]
        # cas 3: {"id-cmde": "..."} (au cas où)
        elif "id-cmde" in j and isinstance(j["id-cmde"], (str, int)):
            cmde = j["id-cmde"]

    if not cmde:
        raise RuntimeError(f"Unexpected response for commande: {j}")

    return str(cmde)


def _fetch_csv(cmde_id: str) -> pd.DataFrame:
    """Télécharge le CSV et renvoie un DataFrame brut (colonnes MF)."""
    r = requests.get(URL_FICHIER, headers=HEADERS, params={"id-cmde": cmde_id}, timeout=120)
    r.raise_for_status()
    # CSV MF : séparateur ';', décimales avec ',', et très important :
    # forcer DATE/HHMN en string pour préserver les zéros à gauche
    df = pd.read_csv(
        BytesIO(r.content),
        sep=";",
        decimal=",",
        dtype={"DATE": "string", "HHMN": "string"}  # <- clé pour éviter l'erreur de parsing
    )
    return df

def _transform_to_records(df: pd.DataFrame) -> List[Tuple[pd.Timestamp, float]]:
    """
    Convertit un DataFrame CSV Météo-France (6 minutes) en liste [(ts_utc, rainfall_mm)].

    Gère plusieurs schémas :
      1) Colonnes 'DATE' (YYYYMMDD) + 'HHMN' (HHMM) + 'RR6'
      2) Colonne 'DATETIME' en ISO (rare)
      3) Colonne 'DATE' déjà concaténée 'YYYYMMDDHHMM' ou 'YYYYMMDD' seule (fallback)

    Retour : timestamps en UTC, pluie (mm) >= 0, ordonné, sans doublons.
    """
    # Normaliser noms de colonnes en upper sans espaces
    df = df.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]

    # Pluie : la colonne est souvent 'RR6'
    rain_col = None
    for c in ("RR6", "RAIN_6MIN", "RAIN", "PRECIP", "RR", "RR_6"):
        if c in df.columns:
            rain_col = c
            break
    if rain_col is None:
        raise RuntimeError(f"Rain column not found. Columns: {list(df.columns)}")

    # --------------- Construire le timestamp UTC ---------------
    ts = None

    # cas 1) DATE + HHMN
    if "DATE" in df.columns and "HHMN" in df.columns:
        # forcer string pour conserver les zéros (ex: '0000')
        df["DATE"] = df["DATE"].astype(str).str.strip()
        df["HHMN"] = df["HHMN"].astype(str).str.strip().str.zfill(4)
        ts_str = df["DATE"] + df["HHMN"]  # 'YYYYMMDDHHMM'
        ts = pd.to_datetime(ts_str, format="%Y%m%d%H%M", utc=True)

    # cas 2) DATETIME ISO
    elif "DATETIME" in df.columns:
        ts = pd.to_datetime(df["DATETIME"], utc=True, errors="coerce")

    # cas 3) DATE seule (parfois déjà concaténée 'YYYYMMDDHHMM' ou juste 'YYYYMMDD')
    elif "DATE" in df.columns:
        df["DATE"] = df["DATE"].astype(str).str.strip()
        # si longueur 12 → 'YYYYMMDDHHMM'
        mask_12 = df["DATE"].str.len() == 12
        ts = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")
        if mask_12.any():
            ts.loc[mask_12] = pd.to_datetime(df.loc[mask_12, "DATE"], format="%Y%m%d%H%M", utc=True, errors="coerce")
        # si longueur 8 → 'YYYYMMDD' → on met '0000' pour HHMN
        mask_8 = df["DATE"].str.len() == 8
        if mask_8.any():
            ts.loc[mask_8] = pd.to_datetime(df.loc[mask_8, "DATE"] + "0000", format="%Y%m%d%H%M", utc=True, errors="coerce")

    else:
        raise RuntimeError(f"No usable date/time columns in CSV. Columns: {list(df.columns)}")

    if ts is None:
        raise RuntimeError("Failed to build timestamps from CSV.")

    # --------------- Nettoyer la pluie ---------------
    rain = df[rain_col]
    # si la pluie a des virgules décimales
    if rain.dtype == object:
        rain = rain.astype(str).str.replace(",", ".", regex=False)
    rain = pd.to_numeric(rain, errors="coerce")

    # --------------- Fusion & filtres ---------------
    out = pd.DataFrame({"ts": ts, "rain": rain}).dropna(subset=["ts"])
    # mm >= 0
    out = out[out["rain"].ge(0)]

    # Aligner sur 6 minutes (sécurité)
    # 360s = 6 min
    # on garde uniquement les timestamps alignés pile sur un pas de 6 minutes
    aligned = (out["ts"].dt.second == 0) & (out["ts"].dt.minute % 6 == 0)
    out = out[aligned]

    # Dédupliquer par timestamp (si doublons)
    out = out.sort_values("ts").drop_duplicates(subset=["ts"], keep="last")

    # Retour en liste de tuples (Timestamp UTC, float)
    return list(out.itertuples(index=False, name=None))


def _upsert_rain(db: Session, station_id: int, recs: Iterable[tuple]) -> int:
    """
    UPSERT sur (station_id, ts_utc).
    `recs` doit être une liste de tuples: [(ts_utc: Timestamp, rainfall_mm: float), ...]
    """
    recs = list(recs)
    if not recs:
        return 0

    # Convert tuple records -> dicts for bulk insert
    values = [
        {"station_id": station_id, "ts_utc": ts, "rainfall_mm": rain}
        for (ts, rain) in recs
    ]

    stmt = pg_insert(Rainfall6Min.__table__).values(values).on_conflict_do_nothing(
        index_elements=["station_id", "ts_utc"]
    )
    db.execute(stmt)
    db.commit()
    # We can’t know how many were ignored; return the attempted insert count.
    return len(values)


def fetch_and_store_for_station(db: Session, station_code: str, day_utc: date) -> dict:
    logger.info(f"[rain] fetch start station={station_code} day_utc={day_utc}")
    _ensure_apikey()

    station = db.query(WeatherStation).filter(
        WeatherStation.weather_station_code == station_code
    ).first()
    if not station:
        raise RuntimeError(f"Station '{station_code}' not found")

    start = datetime(day_utc.year, day_utc.month, day_utc.day, tzinfo=timezone.utc)
    end   = start + timedelta(days=1)

    cmde_id = _call_commande(
        station_code=station_code,
        start_iso=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_iso=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    logger.info(f"[rain] commande id={cmde_id} station={station_code}")

    df = _fetch_csv(cmde_id)
    logger.info(f"[rain] csv rows={len(df)} station={station_code}")

    recs = _transform_to_records(df)
    logger.info(f"[rain] transformed rows={len(recs)} station={station_code}")

    inserted_try = _upsert_rain(db, station_id=station.id, recs=recs)
    logger.info(f"[rain] upsert done station={station_code} rows_seen={len(recs)} rows_try_inserted={inserted_try}")

    return {"station_id": station.id, "station_code": station_code,"rows_seen": len(recs), "rows_inserted_try": inserted_try}

def fetch_yesterday_for_all_stations():
    """Fonction appelée par le scheduler à 00:30 UTC."""
    _ensure_apikey()
    day = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    db = SessionLocal()
    try:
        stations = db.query(WeatherStation).all()
        out = []
        for s in stations:
            try:
                out.append(fetch_and_store_for_station(db, s.weather_station_code, day))
            except Exception as e:
                out.append({"station_code": s.weather_station_code, "error": str(e)})
        return out
    finally:
        db.close()