import os
import warnings
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("app.face_engine").setLevel(logging.DEBUG)
# Suppress harmless 3rd party deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.database import Base, engine, SessionLocal
from app.config import settings
from app.models import Camera
from app.auth import seed_admin_user
from app.alert_dispatcher import check_alert_configuration_status
from app.weapon_engine import weapon_engine  # Eagerly initialize weapon detection on startup
from app.camera_worker import start_camera
from app.unknown_deactualization import start_deactualization_sweep
from app.unknown_retention_service import start_retention_sweep

from app.routers import (
    auth as auth_router,
    faces,
    camera,
    zones,
    stream,
    health,
    events,
    statistics,
    whatsapp_route,
    telegram_route,
    unknown_persons,
    users as users_router,
    spec_unknowns,
)

# Enable pgvector extension, then create tables on startup
with engine.connect() as conn:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    conn.commit()

Base.metadata.create_all(bind=engine)

# Auto-migration (har startup par safe): purane database ko naye code ke mutabiq karta hai.
_AUTO_MIGRATIONS = [
    "ALTER TABLE events ALTER COLUMN in_zone DROP NOT NULL",
    "ALTER TABLE events ALTER COLUMN in_zone DROP DEFAULT",
    "ALTER TABLE face_embeddings ADD COLUMN IF NOT EXISTS quality_score FLOAT",
    "ALTER TABLE unknown_embeddings ADD COLUMN IF NOT EXISTS quality_score FLOAT",
    "ALTER TABLE unknown_sightings ADD COLUMN IF NOT EXISTS quality_score FLOAT",
]
for _stmt in _AUTO_MIGRATIONS:
    try:
        with engine.connect() as conn:
            conn.execute(text(_stmt))
            conn.commit()
    except Exception as _e:
        print(f"[auto-migrate] skipped: {_stmt} -> {_e}")
seed_admin_user()

# Keep snapshots separated by category on disk
for _subdir in ("known", "unknown", "restricted", "forensic", "weapon", "misc"):
    os.makedirs(f"{settings.SNAPSHOT_DIR}/{_subdir}", exist_ok=True)

app = FastAPI(title="AI-Based Smart CCTV Surveillance System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routers
app.include_router(auth_router.router)
app.include_router(faces.router)
app.include_router(camera.router)
app.include_router(zones.router)
app.include_router(stream.router)
app.include_router(health.router)
app.include_router(events.router)
app.include_router(statistics.router)
app.include_router(whatsapp_route.router)
app.include_router(telegram_route.router)
app.include_router(unknown_persons.router)
app.include_router(users_router.router)
app.include_router(spec_unknowns.router)

# Mount snapshots directory
app.mount("/snapshots", StaticFiles(directory="data/snapshots"), name="snapshots")


@app.on_event("startup")
def log_alert_system_status():
    status = check_alert_configuration_status()
    if not status["any_configured"]:
        print("\033[93m[Alerts] Note: WhatsApp / Telegram credentials not configured in .env. External alerts are disabled.\033[0m")
    else:
        wa_label = "Enabled" if status["whatsapp_configured"] else "Disabled"
        tg_label = "Enabled" if status["telegram_configured"] else "Disabled"
        print(f"\033[92m[Alerts] Notification system initialized: Mode={status['mode']}, Primary={status['primary']}, WhatsApp={wa_label}, Telegram={tg_label}\033[0m")


@app.on_event("startup")
def auto_start_active_cameras():
    db = SessionLocal()
    try:
        active_cams = db.query(Camera).filter(Camera.is_active == True).all()
        for cam in active_cams:
            print(f"\033[96m[Startup] Auto-starting camera {cam.name} (ID: {cam.id}, Source: {cam.source})\033[0m")
            start_camera(cam.id, cam.name, cam.source)
    except Exception as e:
        print(f"\033[91m[Startup] Error auto-starting cameras: {e}\033[0m")
    finally:
        db.close()


@app.on_event("startup")
def start_background_sweeps():
    start_deactualization_sweep()
    start_retention_sweep()


@app.get("/")
def read_root():
    return {"status": "running", "message": "Smart CCTV Surveillance API"}