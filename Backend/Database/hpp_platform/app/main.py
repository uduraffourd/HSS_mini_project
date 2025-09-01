# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import stations, plants, rain
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.workers.rain_worker import fetch_yesterday_for_all_stations
import os
import logging

# 1) Créer l'app d'abord
app = FastAPI(title="HPP API", version="0.1.0")

logger = logging.getLogger("uvicorn.error")

# Un scheduler global lié à la boucle asyncio de FastAPI
scheduler = AsyncIOScheduler(timezone="UTC")  # on planifie en UTC


# 2) Middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # en prod: restreins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = AsyncIOScheduler(timezone=os.getenv("FETCH_CRON_TZ", "UTC"))

def _job_fetch_all_yesterday():
    """
    Job exécuté par le scheduler : récupère les 6-min d'hier pour toutes les stations.
    """
    try:
        res = fetch_yesterday_for_all_stations()
        # Log minimal pour debug
        logger.info("[rain:scheduler] done fetch_yesterday_for_all_stations -> %s", res)
    except Exception as e:
        logger.exception("[rain:scheduler] job failed: %s", e)

# 3) Routes “simples” (facultatif mais pratique)

@app.get("/")
def root():
    return {"ok": True, "message": "HPP API is running. See /docs"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.on_event("startup")
async def on_startup():
    # Démarre le scheduler si pas déjà démarré (utile en mode --reload)
    if not scheduler.running:
        # 00:30 UTC tous les jours
        scheduler.add_job(
            _job_fetch_all_yesterday,
            CronTrigger(hour=0, minute=30),  # UTC
            id="rain_fetch_daily_0030utc",
            replace_existing=True,
            max_instances=1,
            coalesce=True,   # si un run est manqué, on compacte
            misfire_grace_time=3600,  # tolère 1h de retard au réveil
        )
        scheduler.start()
        logger.info("[rain:scheduler] started (runs daily at 00:30 UTC)")

@app.on_event("shutdown")
async def on_shutdown():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("[rain:scheduler] stopped")

@app.get("/admin/scheduler/jobs")
def list_jobs():
    return [{"id": j.id,
             "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None}
            for j in scheduler.get_jobs()]

# 4) Importer les routers APRÈS avoir créé app
from app.api.stations import router as stations_router  # noqa: E402
from app.api.plants   import router as plants_router    # noqa: E402
from app.api.rain     import router as rain_router      # noqa: E402
from app.api.rain_debug import router as rain_debug_router  # noqa: E402
from app.api.rain import router as admin_router  # selon le nom de ton fichier

# 5) Monter les routers
app.include_router(stations_router)
app.include_router(plants_router)
app.include_router(rain_router)
app.include_router(rain_debug_router)  # <= nouveau
app.include_router(admin_router)

# 6) Lancement direct (optionnel)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)

