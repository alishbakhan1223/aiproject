"""
Unknown Deactualization: background sweep that marks UnknownPerson rows
as "inactive" once they haven't been seen for a while (left every camera's
view), keeping active-tracking memory/lists clean. Nothing is ever
deleted — sightings, embeddings and snapshots stay on disk/DB; only the
`status` flag flips, and it flips back to "active" automatically the
next time resolve_unknown_person() matches them again.

FILE PATH: backend/app/unknown_deactualization.py
ACTION: CREATE NEW FILE
"""
import threading
import time
import logging
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models import UnknownPerson
from app.config import settings

logger = logging.getLogger(__name__)

_sweep_thread = None
_running = False


def _sweep_once():
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(
            seconds=settings.UNKNOWN_INACTIVITY_TIMEOUT_SECONDS
        )
        stale = (
            db.query(UnknownPerson)
            .filter(UnknownPerson.status == "active")
            .filter(UnknownPerson.last_seen < cutoff)
            .all()
        )
        for person in stale:
            person.status = "inactive"
            logger.info(f"[Deactualization] Unknown-{person.id:03d} marked inactive (last seen {person.last_seen})")
        if stale:
            db.commit()
    except Exception as e:
        logger.error(f"[Deactualization] Sweep error: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


def _sweep_loop():
    logger.info("[Deactualization] Background sweep thread started")
    while _running:
        _sweep_once()
        time.sleep(settings.UNKNOWN_DEACTUALIZATION_SWEEP_SECONDS)


def start_deactualization_sweep():
    global _sweep_thread, _running
    if _running:
        return
    _running = True
    _sweep_thread = threading.Thread(target=_sweep_loop, daemon=True, name="unknown-deactualization")
    _sweep_thread.start()


def stop_deactualization_sweep():
    global _running
    _running = False