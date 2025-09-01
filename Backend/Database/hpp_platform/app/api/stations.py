# app/api/stations.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import WeatherStation
from app.workers.rain_worker import fetch_and_store_for_station

router = APIRouter(prefix="/stations", tags=["stations"])


# -------------------- DB Session dep --------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------- Schemas --------------------
class StationPatch(BaseModel):
    weather_station_name: str | None = None
    new_weather_station_code: str | None = None

    @field_validator("new_weather_station_code")
    @classmethod
    def new_code_digits(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v2 = v.strip()
        if not v2.isdigit():
            raise ValueError("new_weather_station_code must be numeric.")
        if not (5 <= len(v2) <= 10):
            raise ValueError("new_weather_station_code length looks wrong (expect 5–10 digits).")
        return v2


class StationCreate(BaseModel):
    weather_station_code: str
    weather_station_name: str

    @field_validator("weather_station_code")
    @classmethod
    def code_must_be_digits(cls, v: str) -> str:
        v2 = v.strip()
        if not v2.isdigit():
            raise ValueError(
                "weather_station_code must be the numeric station id from Météo-France (e.g. 70473001)."
            )
        if not (5 <= len(v2) <= 10):
            raise ValueError("weather_station_code length looks wrong (expect 5–10 digits).")
        return v2


# -------------------- Helpers --------------------
def _kickstart_fetch_yesterday_async(station_code: str):
    """
    Tâche de fond : ouvre sa propre session, fetch & store la veille UTC.
    Ne doit jamais faire planter la requête principale (log si erreur).
    """
    _db = SessionLocal()
    try:
        day = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        fetch_and_store_for_station(_db, station_code, day)
        print(f"[rain:init] ok station={station_code} day={day}")
    except Exception as e:
        print(f"[rain:init] failed station={station_code}: {e}")
    finally:
        _db.close()


# -------------------- Routes --------------------
@router.post("", response_model=dict)
def create_station(payload: StationCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    code = payload.weather_station_code.strip()
    name = payload.weather_station_name.strip()

    # existe déjà ?
    exists = (
        db.query(WeatherStation)
        .filter(WeatherStation.weather_station_code == code)
        .first()
    )
    if exists:
        # On déclenche quand même un fetch "veille" pour initialiser les données si besoin
        background_tasks.add_task(_kickstart_fetch_yesterday_async, code)
        return {"status": "exists", "id": exists.id}

    # création
    s = WeatherStation(
        weather_station_code=code,
        weather_station_name=name,
    )
    db.add(s)
    db.commit()
    db.refresh(s)

    # Tâche de fond : fetch des données 6min d'hier (UTC) après réponse
    background_tasks.add_task(_kickstart_fetch_yesterday_async, s.weather_station_code)

    return {"status": "created", "id": s.id}


@router.get("", response_model=list[dict])
def list_stations(db: Session = Depends(get_db)):
    rows = db.query(WeatherStation).order_by(WeatherStation.id).all()
    return [
        {
            "id": s.id,
            "weather_station_code": s.weather_station_code,
            "weather_station_name": s.weather_station_name,
            "created_at": s.created_at,
        }
        for s in rows
    ]


@router.patch("/{weather_station_code}", response_model=dict)
def patch_station(weather_station_code: str, payload: StationPatch, db: Session = Depends(get_db)):
    s = (
        db.query(WeatherStation)
        .filter(WeatherStation.weather_station_code == weather_station_code)
        .first()
    )
    if not s:
        raise HTTPException(404, detail="station not found")

    if payload.weather_station_name is not None:
        s.weather_station_name = payload.weather_station_name.strip()

    if payload.new_weather_station_code is not None:
        new_code = payload.new_weather_station_code.strip()
        # unicité
        exists = (
            db.query(WeatherStation)
            .filter(WeatherStation.weather_station_code == new_code)
            .first()
        )
        if exists and exists.id != s.id:
            raise HTTPException(409, detail="new_weather_station_code already exists")
        s.weather_station_code = new_code

    db.commit()
    return {"status": "updated", "id": s.id}


@router.delete("/{weather_station_code}", response_model=dict)
def delete_station(weather_station_code: str, db: Session = Depends(get_db)):
    s = (
        db.query(WeatherStation)
        .filter(WeatherStation.weather_station_code == weather_station_code)
        .first()
    )
    if not s:
        raise HTTPException(404, detail="station not found")

    # Suppression :
    # - rainfall_6min.station_id doit être défini en ON DELETE CASCADE (au niveau modèle/migration).
    # - plants.station_id doit être en SET NULL (ou CASCADE si tu préfères les supprimer).
    db.delete(s)
    db.commit()
    return {"status": "deleted"}