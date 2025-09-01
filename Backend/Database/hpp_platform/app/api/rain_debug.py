# app/api/rain_debug.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta, timezone
from typing import Optional

from app.db.session import SessionLocal
from app.db.models import WeatherStation, Rainfall6Min
from app.workers.rain_worker import fetch_and_store_for_station

router = APIRouter(prefix="/rain", tags=["rain-debug"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/debug/{station_code}")
def rain_debug(station_code: str, db: Session = Depends(get_db)):
    st = db.query(WeatherStation).filter(
        WeatherStation.weather_station_code == station_code
    ).first()
    if not st:
        raise HTTPException(404, "station not found")

    q = db.query(Rainfall6Min).filter(Rainfall6Min.station_id == st.id)
    cnt = q.count()
    row_min = q.order_by(Rainfall6Min.ts_utc.asc()).first()
    row_max = q.order_by(Rainfall6Min.ts_utc.desc()).first()
    return {
        "station_id": st.id,
        "station_code": st.weather_station_code,
        "rows": cnt,
        "min_ts": row_min.ts_utc if row_min else None,
        "max_ts": row_max.ts_utc if row_max else None,
    }

@router.post("/fetch_yesterday/{station_code}")
def fetch_yesterday(station_code: str, db: Session = Depends(get_db)):
    day = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    res = fetch_and_store_for_station(db, station_code, day)
    return {"ok": True, "details": res}

@router.post("/backfill/{station_code}")
def backfill_days(station_code: str, days: int = 7, db: Session = Depends(get_db)):
    # récupère N jours en arrière, 1 par 1
    today = datetime.now(timezone.utc).date()
    out = []
    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        out.append(fetch_and_store_for_station(db, station_code, d))
    return {"ok": True, "runs": out}