# app/api/rain.py
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import SessionLocal
from app.db.models import Rainfall6Min, WeatherStation
from app.workers.rain_worker import fetch_yesterday_for_all_stations

router = APIRouter(prefix="/admin", tags=["admin"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/scheduler/run-now")
def scheduler_run_now():
    res = fetch_yesterday_for_all_stations()
    return {"ok": True, "details": res}

def _resolve_station_id(db: Session, weather_station_code: str | None, station_id: int | None) -> int:
    if weather_station_code:
        ws = db.query(WeatherStation).filter(WeatherStation.weather_station_code == weather_station_code).first()
        if not ws:
            raise HTTPException(404, detail="weather_station_code not found")
        return ws.id
    if station_id is not None:
        ws = db.get(WeatherStation, station_id)
        if not ws:
            raise HTTPException(404, detail="station_id not found")
        return station_id
    raise HTTPException(400, detail="Provide weather_station_code or station_id")

@router.get("")
def get_rain(
    weather_station_code: str | None = Query(None, description="Code réel de station (externe)"),
    station_id: int | None = Query(None, description="ID interne de station (FK)"),
    start: datetime = Query(..., description="UTC ISO8601, ex: 2025-08-30T00:00:00Z"),
    end: datetime = Query(..., description="UTC ISO8601, ex: 2025-08-31T00:00:00Z"),
    step: str = Query("6min", pattern="^(6min|hour|day)$"),
    db: Session = Depends(get_db),
):
    if start >= end:
        raise HTTPException(400, detail="`start` must be strictly earlier than `end`.")

    sid = _resolve_station_id(db, weather_station_code, station_id)

    if step == "6min":
        q = (
            db.query(Rainfall6Min)
              .filter(Rainfall6Min.station_id == sid)
              .filter(Rainfall6Min.ts_utc >= start)
              .filter(Rainfall6Min.ts_utc < end)
              .order_by(Rainfall6Min.ts_utc)
        )
        return [{"ts_utc": r.ts_utc, "mm": r.rainfall_mm} for r in q.all()]

    bucket = "hour" if step == "hour" else "day"
    sql = text(f"""
        SELECT date_trunc('{bucket}', ts_utc) AS bucket, SUM(rainfall_mm) AS mm
        FROM rainfall_6min
        WHERE station_id = :sid
          AND ts_utc >= :start AND ts_utc < :end
        GROUP BY 1
        ORDER BY 1
    """)
    rows = db.execute(sql, {"sid": sid, "start": start, "end": end}).all()
    return [{"ts_utc": r.bucket, "mm": float(r.mm)} for r in rows]

# 🔹 Nouveau endpoint pour debug complet
@router.get("/rain-all")
def get_all_rain(db: Session = Depends(get_db)):
    """Retourne toutes les lignes de rainfall_6min (debug uniquement)."""
    q = db.query(Rainfall6Min).order_by(Rainfall6Min.ts_utc).all()
    return [
        {
            "id": r.id,
            "station_id": r.station_id,
            "ts_utc": r.ts_utc,
            "rainfall_mm": r.rainfall_mm,
        }
        for r in q
    ]