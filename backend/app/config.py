import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from backend/ or project root directory with forced override
_backend_env = Path(__file__).resolve().parent.parent / ".env"
_root_env = Path(__file__).resolve().parent.parent.parent / ".env"

if _root_env.is_file():
    load_dotenv(dotenv_path=_root_env, override=True)
elif _backend_env.is_file():
    load_dotenv(dotenv_path=_backend_env, override=True)
else:
    load_dotenv(override=True)


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://cctv:cctv123@localhost:5432/cctv_db"
    )

    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_STREAM_NAME: str = os.getenv("REDIS_STREAM_NAME", "cctv_events")

    # --- Meta WhatsApp Alerts ---
    WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "").strip().strip('"').strip("'")
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip().strip('"').strip("'")
    WHATSAPP_ADMIN_NUMBER: str = os.getenv("WHATSAPP_ADMIN_NUMBER", "").strip().strip('"').strip("'")

    # --- Telegram Alerts ---
    TELEGRAM_ENABLED: bool = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("true", "1", "yes")
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip().strip('"').strip("'")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip().strip('"').strip("'")

    # --- Alert Fallback / Dispatcher Settings ---
    ALERT_MODE: str = os.getenv("ALERT_MODE", "fallback").lower()  # "fallback" or "broadcast"
    PRIMARY_ALERT_PROVIDER: str = os.getenv("PRIMARY_ALERT_PROVIDER", "whatsapp").lower()  # "whatsapp" or "telegram"

    UNKNOWN_FACE_THRESHOLD: float = float(os.getenv("UNKNOWN_FACE_THRESHOLD", 0.45))
    UNKNOWN_PERSON_DISTANCE_THRESHOLD: float = float(os.getenv("UNKNOWN_PERSON_DISTANCE_THRESHOLD", 0.50))

    # --- Strict frontal-face & quality filtering ---
    # Tuned to accept faces from ~2 feet up to ~10-12 feet (typical CCTV
    # mounting distance), not just close-range webcam-style testing.
    #
    # FACE_MAX_ROLL_DEG is intentionally very permissive: this camera's
    # frames come in rotated ~90 degrees, so InsightFace reports roll of
    # roughly -80 to -100 for every single face even when yaw/pitch are
    # small (i.e. the person IS facing the camera). Roll does not degrade
    # recognition accuracy — InsightFace aligns the crop internally using
    # landmarks before generating the embedding — so gating hard on roll
    # was rejecting every face while providing no real accuracy benefit.
    FACE_MAX_YAW_DEG: float = float(os.getenv("FACE_MAX_YAW_DEG", 35))
    FACE_MAX_PITCH_DEG: float = float(os.getenv("FACE_MAX_PITCH_DEG", 35))
    FACE_MAX_ROLL_DEG: float = float(os.getenv("FACE_MAX_ROLL_DEG", 110))
    FACE_MIN_DET_SCORE: float = float(os.getenv("FACE_MIN_DET_SCORE", 0.50))
    FACE_MIN_SHARPNESS: float = float(os.getenv("FACE_MIN_SHARPNESS", 20.0))
    FACE_MIN_QUALITY_SCORE: float = float(os.getenv("FACE_MIN_QUALITY_SCORE", 40.0))
    FACE_MIN_SIZE_PX: int = int(os.getenv("FACE_MIN_SIZE_PX", 32))

    # Compatibility aliases
    MIN_BLUR_SCORE: float = FACE_MIN_SHARPNESS
    MIN_FACE_SIZE: int = FACE_MIN_SIZE_PX
    MIN_DETECTION_CONFIDENCE: float = FACE_MIN_DET_SCORE
    MAX_YAW_DEGREES: float = FACE_MAX_YAW_DEG
    MAX_PITCH_DEGREES: float = FACE_MAX_PITCH_DEG

    RESTRICTED_OBJECTS: list = [
        o.strip().lower()
        for o in os.getenv("RESTRICTED_OBJECTS", "knife,gun,backpack").split(",")
    ]
    CONFIDENCE_THRESHOLD: float = float(os.getenv("CONFIDENCE_THRESHOLD", 0.4))

    # Two-tier detection
    LIGHT_MODEL: str = os.getenv("LIGHT_MODEL", "yolov8n.pt")
    FORENSIC_MODEL: str = os.getenv("FORENSIC_MODEL", "yolov8m.pt")

    # --- Weapon Detection ---
    WEAPON_DETECTION_ENABLED: bool = os.getenv("WEAPON_DETECTION_ENABLED", "true").lower() in ("true", "1", "yes")
    WEAPON_MODEL_PATH: str = os.getenv("WEAPON_MODEL_PATH", "models/weapon/threat-yolov8n.pt")
    WEAPON_CONFIDENCE: float = float(os.getenv("WEAPON_CONFIDENCE", "0.50"))
    WEAPON_INFERENCE_SIZE: int = int(os.getenv("WEAPON_INFERENCE_SIZE", "1024"))
    WEAPON_MULTI_SCALE_ENABLED: bool = os.getenv("WEAPON_MULTI_SCALE_ENABLED", "true").lower() in ("true", "1", "yes")
    WEAPON_NMS_IOU: float = float(os.getenv("WEAPON_NMS_IOU", "0.45"))
    WEAPON_CONFIRMATION_COUNT: int = int(os.getenv("WEAPON_CONFIRMATION_COUNT", "2"))
    WEAPON_CONFIRMATION_WINDOW_SECONDS: float = float(os.getenv("WEAPON_CONFIRMATION_WINDOW_SECONDS", "4.0"))
    WEAPON_COOLDOWN_SECONDS: float = float(os.getenv("WEAPON_COOLDOWN_SECONDS", "30.0"))
    WEAPON_CLASSES: str = os.getenv("WEAPON_CLASSES", "Gun")
    WEAPON_FORENSIC_ENABLED: bool = os.getenv("WEAPON_FORENSIC_ENABLED", "true").lower() in ("true", "1", "yes")

    SNAPSHOT_DIR: str = os.getenv("SNAPSHOT_DIR", "data/snapshots")

    # --- Unknown Deactualization ---
    UNKNOWN_INACTIVITY_TIMEOUT_SECONDS: float = float(
        os.getenv("UNKNOWN_INACTIVITY_TIMEOUT_SECONDS", "60")
    )
    UNKNOWN_DEACTUALIZATION_SWEEP_SECONDS: float = float(
        os.getenv("UNKNOWN_DEACTUALIZATION_SWEEP_SECONDS", "15")
    )
    UNKNOWN_DEACTUALIZE_MISSED_FRAMES: int = int(
        os.getenv("UNKNOWN_DEACTUALIZE_MISSED_FRAMES", "30")
    )

    # --- Auth ---
    JWT_SECRET: str = os.getenv("JWT_SECRET", "change-this-secret-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", 480))
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "cctv2024")

    # --- Business Rules: Revert Lock & Unknown Retention ---
    REVERT_WINDOW_HOURS: float = float(os.getenv("REVERT_WINDOW_HOURS", "48"))
    MAPPING_WINDOW_DAYS: int = int(os.getenv("MAPPING_WINDOW_DAYS", "30"))
    MAPPING_DAYS: int = int(os.getenv("MAPPING_DAYS", str(MAPPING_WINDOW_DAYS)))
    AUTO_DELETE_UNKNOWN_ENABLED: bool = os.getenv("AUTO_DELETE_UNKNOWN_ENABLED", "false").lower() in ("true", "1", "yes")
    AUTO_DELETE_SWEEP_INTERVAL_SECONDS: int = int(os.getenv("AUTO_DELETE_SWEEP_INTERVAL_SECONDS", "3600"))


settings = Settings()
os.makedirs(settings.SNAPSHOT_DIR, exist_ok=True)