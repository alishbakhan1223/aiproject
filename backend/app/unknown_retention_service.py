"""
Rule 2: 30-Day Mapping Window + Auto-Delete (Cooldown).
Unmapped unknown identities older than 30 days are automatically deleted.
- Age base: unknowns.date_time if available, else unknown_persons.first_seen.
- Never deletes mapped/actualization rows or audit trail.
- Removes: unknown_persons (along with sightings and embeddings), disk folder, unknowns row.
- Disabled by default via AUTO_DELETE_UNKNOWN_ENABLED until explicitly confirmed.
"""
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)
PKT = timezone(timedelta(hours=5))

_retention_thread = None
_running = False


def get_expired_unmapped_unknowns(
    db: Session, now: datetime | None = None, days: int | None = None
) -> list[dict]:
    """
    Returns the list of unmapped unknowns that are older than `days` (default: 30 days).
    Does NOT modify or delete anything (safe for dry-run inspection).
    """
    if days is None:
        days = getattr(settings, "MAPPING_WINDOW_DAYS", 30)

    current_time = now if now is not None else datetime.now(PKT).replace(tzinfo=None)
    cutoff = current_time - timedelta(days=days)

    # 1. UnknownPerson rows with no actualization record and older than cutoff
    sql = text("""
        SELECT 
            up.id AS unknown_person_id,
            u.unknown_id,
            COALESCE(u.date_time, up.first_seen + INTERVAL '5 hour') AS base_date,
            ROUND(EXTRACT(EPOCH FROM (:now - COALESCE(u.date_time, up.first_seen + INTERVAL '5 hour'))) / 86400.0, 1) AS age_days
        FROM unknown_persons up
        LEFT JOIN unknowns u ON u.insight_id = 'unknown-person-' || CAST(up.id AS text)
        WHERE COALESCE(u.date_time, up.first_seen + INTERVAL '5 hour') < :cutoff
          AND NOT EXISTS (
              SELECT 1 FROM actualization a
              WHERE a.unkn_id = u.unknown_id
                 OR a.unkn_id IN (
                     SELECT unk2.unknown_id FROM unknowns unk2
                     WHERE unk2.insight_id = 'unknown-person-' || CAST(up.id AS text)
                 )
          )
        ORDER BY up.id
    """)

    rows = db.execute(sql, {"now": current_time, "cutoff": cutoff}).fetchall()
    results = []
    for r in rows:
        results.append({
            "unknown_person_id": r.unknown_person_id,
            "unknown_id": r.unknown_id,
            "base_date": r.base_date,
            "age_days": float(r.age_days) if r.age_days is not None else 0.0,
        })
    return results


def cleanup_expired_unknowns(
    db: Session, now: datetime | None = None, days: int | None = None, dry_run: bool = False
) -> list[dict]:
    """
    Deletes unmapped unknowns older than 30 days.
    If dry_run=True, returns the candidates without performing any deletion.
    """
    candidates = get_expired_unmapped_unknowns(db, now=now, days=days)
    if dry_run or not candidates:
        return candidates

    deleted = []
    for item in candidates:
        pid = item["unknown_person_id"]
        uid = item["unknown_id"]
        age = item["age_days"]

        logger.info(
            f"[Retention] Auto-deleting expired unmapped unknown person ID={pid}, "
            f"unknown_id={uid}, age={age} days"
        )

        try:
            # 1. Child embeddings
            db.execute(
                text("DELETE FROM unknown_embeddings WHERE unknown_person_id = :pid"),
                {"pid": pid},
            )
            # 2. Child sightings
            db.execute(
                text("DELETE FROM unknown_sightings WHERE unknown_person_id = :pid"),
                {"pid": pid},
            )
            # 3. unknowns row
            if uid:
                db.execute(
                    text("DELETE FROM unknowns WHERE unknown_id = :uid"),
                    {"uid": uid},
                )
            else:
                db.execute(
                    text("DELETE FROM unknowns WHERE insight_id = :i"),
                    {"i": f"unknown-person-{pid}"},
                )
            # 4. unknown_persons row
            db.execute(
                text("DELETE FROM unknown_persons WHERE id = :pid"),
                {"pid": pid},
            )

            # 5. Snapshots folder on disk
            folder = os.path.join(settings.SNAPSHOT_DIR, "unknown", f"Unknown-{pid:03d}")
            if os.path.exists(folder):
                try:
                    shutil.rmtree(folder, ignore_errors=True)
                except Exception as fe:
                    logger.warning(f"[Retention] Failed to remove folder {folder}: {fe}")

            db.commit()
            deleted.append(item)
            logger.info(f"[Retention] Successfully deleted expired Unknown-{pid:03d} (age: {age} days)")
        except Exception as e:
            db.rollback()
            logger.error(f"[Retention] Error deleting unknown person ID={pid}: {e}", exc_info=True)

    return deleted


def _retention_sweep_once():
    """Runs a single retention check."""
    if not getattr(settings, "AUTO_DELETE_UNKNOWN_ENABLED", False):
        logger.debug("[Retention] Auto-delete job is disabled in settings (AUTO_DELETE_UNKNOWN_ENABLED=False)")
        return

    db = SessionLocal()
    try:
        logger.info("[Retention] Running scheduled auto-delete sweep for unmapped unknowns older than 30 days...")
        deleted = cleanup_expired_unknowns(db, dry_run=False)
        logger.info(f"[Retention] Scheduled sweep finished. {len(deleted)} expired unknown(s) removed.")
    except Exception as e:
        logger.error(f"[Retention] Retention sweep error: {e}", exc_info=True)
    finally:
        db.close()


def _retention_loop():
    logger.info("[Retention] Background retention sweep thread started")
    interval = getattr(settings, "AUTO_DELETE_SWEEP_INTERVAL_SECONDS", 3600)
    # Run once at startup
    _retention_sweep_once()
    while _running:
        time.sleep(interval)
        if _running:
            _retention_sweep_once()


def start_retention_sweep():
    global _retention_thread, _running
    if _running:
        return
    _running = True
    _retention_thread = threading.Thread(
        target=_retention_loop, daemon=True, name="unknown-retention-sweep"
    )
    _retention_thread.start()


def stop_retention_sweep():
    global _running
    _running = False

