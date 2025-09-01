# app/api/plants.py
from fastapi import APIRouter, HTTPException, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import HydropowerPlant, WeatherStation

router = APIRouter(prefix="/plants", tags=["plants"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- Schemas ----------
class PlantCreate(BaseModel):
    hpp_code: str = Field(..., description="Code réel (externe) de la centrale, unique et modifiable")
    hpp_name: str
    weather_station_id: int | None = Field(
        None, description="PK interne de la station météo (optionnel). Si fourni, doit exister."
    )

class PlantPatch(BaseModel):
    hpp_name: str | None = None
    weather_station_id: int | None = Field(
        default=None,
        description="Si présent dans le payload: None => délinker, int => lier à cette station",
    )
    new_hpp_code: str | None = None

# ---------- Helpers ----------
def _assert_station_exists(db: Session, station_id: int) -> None:
    if not db.get(WeatherStation, station_id):
        raise HTTPException(404, detail=f"weather_station_id {station_id} not found")

# ---------- Routes ----------
@router.post("", response_model=dict)
def create_plant(payload: PlantCreate, db: Session = Depends(get_db)):
    if db.query(HydropowerPlant).filter(HydropowerPlant.hpp_code == payload.hpp_code).first():
        raise HTTPException(409, detail="hpp_code already exists")

    if payload.weather_station_id is not None:
        _assert_station_exists(db, payload.weather_station_id)

    plant = HydropowerPlant(
        hpp_code=payload.hpp_code,
        hpp_name=payload.hpp_name,
        weather_station_id=payload.weather_station_id,  # <- on stocke la FK interne
    )
    db.add(plant)
    db.commit()
    db.refresh(plant)
    return {"id": plant.id, "status": "created"}

@router.get("", response_model=list[dict])
def list_plants(db: Session = Depends(get_db)):
    plants = db.query(HydropowerPlant).all()
    return [
        {
            "id": p.id,
            "hpp_code": p.hpp_code,
            "hpp_name": p.hpp_name,
            "weather_station_id": p.weather_station_id,  # <- uniquement l'id
        }
        for p in plants
    ]

@router.get("/{hpp_code}", response_model=dict)
def get_plant(hpp_code: str = Path(...), db: Session = Depends(get_db)):
    p = db.query(HydropowerPlant).filter(HydropowerPlant.hpp_code == hpp_code).first()
    if not p:
        raise HTTPException(404, detail="plant not found")
    return {
        "id": p.id,
        "hpp_code": p.hpp_code,
        "hpp_name": p.hpp_name,
        "weather_station_id": p.weather_station_id,
    }

@router.patch("/{hpp_code}", response_model=dict)
def patch_plant(hpp_code: str, payload: PlantPatch, db: Session = Depends(get_db)):
    p = db.query(HydropowerPlant).filter(HydropowerPlant.hpp_code == hpp_code).first()
    if not p:
        raise HTTPException(404, "plant not found")

    data = payload.model_dump(exclude_unset=True)

    # 1) Nom
    if "hpp_name" in data:
        new_name = (data["hpp_name"] or "").strip()
        if not new_name:
            raise HTTPException(400, "hpp_name cannot be empty")
        p.hpp_name = new_name

    # 2) Station météo via ID (si la clé est présente dans le payload)
    if "weather_station_id" in data:
        ws_id = data["weather_station_id"]
        if ws_id is None:
            # délinker explicitement
            p.weather_station_id = None
        else:
            _assert_station_exists(db, ws_id)
            p.weather_station_id = ws_id

    # 3) Changement de code de la centrale
    if "new_hpp_code" in data:
        new_code = (data["new_hpp_code"] or "").strip()
        if not new_code:
            raise HTTPException(400, "new_hpp_code cannot be empty")
        exists = db.query(HydropowerPlant).filter(HydropowerPlant.hpp_code == new_code).first()
        if exists and exists.id != p.id:
            raise HTTPException(409, "new_hpp_code already exists")
        p.hpp_code = new_code

    db.commit()
    db.refresh(p)

    return {
        "status": "updated",
        "id": p.id,
        "hpp_code": p.hpp_code,
        "hpp_name": p.hpp_name,
        "weather_station_id": p.weather_station_id,
    }

@router.delete("/{hpp_code}", response_model=dict)
def delete_plant(hpp_code: str, db: Session = Depends(get_db)):
    p = db.query(HydropowerPlant).filter(HydropowerPlant.hpp_code == hpp_code).first()
    if not p:
        raise HTTPException(404, detail="plant not found")
    db.delete(p)
    db.commit()
    return {"status": "deleted"}