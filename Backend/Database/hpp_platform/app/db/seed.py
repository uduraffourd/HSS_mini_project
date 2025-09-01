from app.db.session import SessionLocal
from app.db.models import WeatherStation

def run():
    db = SessionLocal()
    try:
        data = [("FR_12345", "Station Demo 1"), ("FR_67890", "Station Demo 2")]
        for code, name in data:
            exists = db.query(WeatherStation).filter(
                WeatherStation.weather_station_code == code
            ).first()
            if not exists:
                db.add(WeatherStation(
                    weather_station_code=code,
                    weather_station_name=name
                ))
        db.commit()
        print("Seed OK")
    finally:
        db.close()

if __name__ == "__main__":
    run()