"""
Map -> actualization mein row. Undo -> row hat jaye, unknown wahi ID ke saath.
Ye functions kabhi error bahar nahi phenkte (purana code na toote).
Business Rules:
- 48-Hour Revert Lock: Mapping ke 48 ghante baad revert, remove, delete sab block.
- 30-Day Mapping Window: Detection ke 30 din baad mapping mana (check_mapping_window).
- Status rule: Detection se 48h ke andar map hone par 'Successful', warna 'Unsuccessful'.
"""
import logging
import os
import shutil
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal

MAX_FACE_IMAGES = 4  # unknown_person_service.MAX_FACE_IMAGES ke barabar rakho

logger = logging.getLogger(__name__)
PKT = timezone(timedelta(hours=5))


def _insight(unknown_person_id: int) -> str:
    return f"unknown-person-{unknown_person_id}"


def check_mapping_window(unknown_person_id: int, db=None, now: datetime | None = None) -> tuple[bool, str]:
    """
    Rule 2: 30-Day Mapping Window Check.
    Returns (allowed: bool, message: str).
    Base detection time: unknowns.date_time agar maujood ho, warna unknown_persons.first_seen.
    Agar 30 din se zyada guzar gaye hon to mapping block.
    """
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    try:
        current_time = now if now is not None else datetime.now(PKT).replace(tzinfo=None)

        # 1. unknowns row se date_time dekho
        row = db.execute(
            text("SELECT date_time FROM unknowns WHERE insight_id = :i"),
            {"i": _insight(unknown_person_id)},
        ).first()
        det_time = row.date_time if row and row.date_time else None

        # 2. Agar unknowns mein na mila to unknown_persons.first_seen dekho
        if not det_time:
            up_row = db.execute(
                text("SELECT first_seen FROM unknown_persons WHERE id = :id"),
                {"id": unknown_person_id},
            ).first()
            # unknown_persons.first_seen is UTC naive; convert to PKT naive (+5h)
            det_time = (up_row.first_seen + timedelta(hours=5)) if up_row and up_row.first_seen else None

        if not det_time:
            return True, "OK"

        elapsed_days = (current_time - det_time).total_seconds() / 86400.0
        allowed_days = getattr(settings, "MAPPING_WINDOW_DAYS", 30)
        if elapsed_days > allowed_days:
            return (
                False,
                "Mapping window closed: 30 days have passed.",
            )
        return True, "OK"
    except Exception as e:
        logger.error("[actualization] check_mapping_window failed: %s", e, exc_info=True)
        return True, "OK"
    finally:
        if should_close:
            db.close()


def check_revert_lock_for_photo(
    db, source_unknown_id: int | None, now: datetime | None = None
) -> tuple[bool, float | None, str | None]:
    """
    Rule 1: 48-Hour Revert Lock for a single photo.
    Returns (is_locked: bool, hours_left: float | None, error_message: str | None).
    - Agar source_unknown_id None hai (manually registered): no lock (False, None, None).
    - Agar actualization row na mile: no lock (False, None, None).
    - Agar actualization.time_stamp se 48 ghante guzar chuke hon: (True, 0.0, msg).
    - Agar 48 ghante ke andar ho: (False, hours_left, None).
    """
    if source_unknown_id is None:
        return False, None, None

    try:
        current_time = now if now is not None else datetime.now(PKT).replace(tzinfo=None)
        row = db.execute(
            text(
                "SELECT a.time_stamp "
                "FROM actualization a "
                "JOIN unknowns u ON u.unknown_id = a.unkn_id "
                "WHERE u.insight_id = :i "
                "ORDER BY a.time_stamp DESC LIMIT 1"
            ),
            {"i": _insight(source_unknown_id)},
        ).first()

        if not row or not row.time_stamp:
            return False, None, None

        elapsed_seconds = (current_time - row.time_stamp).total_seconds()
        elapsed_hours = elapsed_seconds / 3600.0
        limit_hours = getattr(settings, "REVERT_WINDOW_HOURS", 48.0)

        if elapsed_hours > limit_hours:
            return (
                True,
                0.0,
                "Revert window (48 hours) closed. Changes are not allowed anymore.",
            )
        else:
            hours_left = max(0.0, round(limit_hours - elapsed_hours, 2))
            return False, hours_left, None
    except Exception as e:
        logger.error("[actualization] check_revert_lock_for_photo failed: %s", e, exc_info=True)
        return False, None, None


def check_revert_lock_for_known_face(
    db, known_face_id: int, now: datetime | None = None
) -> tuple[bool, list[int], float | None]:
    """
    Rule 1: 48-Hour Revert Lock for an entire known person.
    Returns (is_locked: bool, locked_photo_ids: list[int], min_hours_left: float | None).
    Agar koi bhi mapped photo 48 ghante se purani ho to poora revert block (True).
    """
    try:
        rows = db.execute(
            text("SELECT id, source_unknown_id FROM face_embeddings WHERE face_id = :fid"),
            {"fid": known_face_id},
        ).all()

        locked_photo_ids = []
        min_hours_left = None

        for r in rows:
            if r.source_unknown_id is not None:
                locked, hours_left, _ = check_revert_lock_for_photo(
                    db, r.source_unknown_id, now=now
                )
                if locked:
                    locked_photo_ids.append(r.id)
                elif hours_left is not None:
                    if min_hours_left is None or hours_left < min_hours_left:
                        min_hours_left = hours_left

        if locked_photo_ids:
            return True, locked_photo_ids, 0.0
        return False, [], min_hours_left
    except Exception as e:
        logger.error("[actualization] check_revert_lock_for_known_face failed: %s", e, exc_info=True)
        return False, [], None


def on_map(unknown_person_id: int, user_code: str, known_id: int | None = None,
           old_info=None, now: datetime | None = None):
    """Unknown ko Known se map karne par call karo.
    Ek unknown ki ek hi mapping row rehti hai (purani ho to pehle hat jati hai).
    Status rule: detection se 48 ghante ke andar map hone par 'Successful', warna 'Unsuccessful'."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT unknown_id, date_time FROM unknowns WHERE insight_id = :i"),
            {"i": _insight(unknown_person_id)},
        ).first()
        if not row:
            logger.warning("[actualization] unknowns mein %s nahi mila", _insight(unknown_person_id))
            return None
        current_now = now if now is not None else datetime.now(PKT).replace(tzinfo=None)

        # Status check: detection time se 48 ghante ke andar = Successful, warna Unsuccessful
        det_time = row.date_time
        if not det_time:
            up_row = db.execute(
                text("SELECT first_seen FROM unknown_persons WHERE id = :id"),
                {"id": unknown_person_id},
            ).first()
            # unknown_persons.first_seen is UTC naive; convert to PKT naive (+5h)
            det_time = (up_row.first_seen + timedelta(hours=5)) if up_row and up_row.first_seen else current_now

        elapsed_hours = (current_now - det_time).total_seconds() / 3600.0
        status = "Successful" if elapsed_hours <= getattr(settings, "REVERT_WINDOW_HOURS", 48.0) else "Unsuccessful"

        # Ek unknown ki ek hi mapping row: purani ho to pehle hatao
        db.execute(text("DELETE FROM actualization WHERE unkn_id = :u"), {"u": row.unknown_id})
        if isinstance(old_info, str):          # purana tareeqa: sirf path
            old_info = {"archived_path": old_info}
        info = old_info or {}
        db.execute(
            text(
                "INSERT INTO actualization (unkn_id, user_code, time_stamp, known_date, "
                "old_picture, status, known_id, old_embedding, old_quality, "
                "old_added_at, old_source_unknown_id) "
                "VALUES (:u, :uc, :ts, :kd, :op, :st, :k, "
                "CAST(:oe AS vector), :oq, :oa, :os)"
            ),
            {"u": row.unknown_id, "uc": str(user_code), "ts": current_now,
             "kd": current_now.date(), "op": info.get("archived_path"), "st": status, "k": known_id,
             "oe": info.get("vector"), "oq": info.get("quality"),
             "oa": info.get("added_at"), "os": info.get("source_unknown_id")},
        )
        db.commit()
        logger.info("[actualization] mapped %s -> known %s with status=%s", row.unknown_id, known_id, status)
        return row.unknown_id
    except Exception as e:
        db.rollback()
        logger.error("[actualization] on_map failed: %s", e, exc_info=True)
        return None
    finally:
        db.close()


def on_undo(unknown_person_id: int, new_unknown_person_id: int | None = None):
    """Mapping hatane (undo) par call karo (unknown id se).
    new_unknown_person_id = agar undo par NAYI id bani ho to wo bhi do.
    """
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT unknown_id FROM unknowns WHERE insight_id = :i"),
            {"i": _insight(unknown_person_id)},
        ).first()
        if not row:
            return None
        db.execute(text("DELETE FROM actualization WHERE unkn_id = :u"), {"u": row.unknown_id})
        if new_unknown_person_id and new_unknown_person_id != unknown_person_id:
            db.execute(
                text("UPDATE unknowns SET insight_id = :n WHERE unknown_id = :u"),
                {"n": _insight(new_unknown_person_id), "u": row.unknown_id},
            )
        db.commit()
        logger.info("[actualization] undo %s", row.unknown_id)
        return row.unknown_id
    except Exception as e:
        db.rollback()
        logger.error("[actualization] on_undo failed: %s", e, exc_info=True)
        return None
    finally:
        db.close()


def on_undo_known(known_face_id: int):
    """Known face ko revert karne par: uski saari actualization rows hata do."""
    db = SessionLocal()
    try:
        res = db.execute(
            text("DELETE FROM actualization WHERE known_id = :k"), {"k": known_face_id}
        )
        db.commit()
        logger.info("[actualization] undo known_id=%s, rows=%s", known_face_id, res.rowcount)
        return res.rowcount
    except Exception as e:
        db.rollback()
        logger.error("[actualization] on_undo_known failed: %s", e, exc_info=True)
        return None
    finally:
        db.close()


def on_delete(unknown_person_id: int):
    """Unknown delete par call karo: actualization pehle, phir unknowns."""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT unknown_id FROM unknowns WHERE insight_id = :i"),
            {"i": _insight(unknown_person_id)},
        ).first()
        if not row:
            return None
        db.execute(text("DELETE FROM actualization WHERE unkn_id = :u"), {"u": row.unknown_id})
        db.execute(text("DELETE FROM unknowns WHERE unknown_id = :u"), {"u": row.unknown_id})
        db.commit()
        return row.unknown_id
    except Exception as e:
        db.rollback()
        logger.error("[actualization] on_delete failed: %s", e, exc_info=True)
        return None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# FIFO: Known ke 4 photo slot bhar jaye aur naya photo aaye to sabse purana
# photo hat jata hai. Wo hatne se pehle archive mein copy hota hai aur uska
# path actualization.old_picture mein save hota hai.
# ---------------------------------------------------------------------------
def snapshot_oldest_before_promote(db, name: str):
    """promote_to_known se PEHLE call karo. Agar known ke slots bhare hain to
    sabse purane photo ki copy archive mein rakh leta hai. Kabhi error nahi phenkta."""
    try:
        rows = db.execute(
            text(
                "SELECT fe.id, fe.photo_path, fe.vector::text AS vec, fe.quality_score, "
                "fe.added_at, fe.source_unknown_id FROM face_embeddings fe "
                "JOIN known_faces kf ON kf.id = fe.face_id "
                "WHERE lower(kf.name) = lower(:n) "
                "ORDER BY fe.added_at ASC, fe.id ASC"
            ),
            {"n": name.strip()},
        ).all()
        if len(rows) < MAX_FACE_IMAGES:
            return None
        oldest = rows[0]
        if not oldest.photo_path or not os.path.exists(oldest.photo_path):
            return None
        archive_dir = os.path.join(settings.SNAPSHOT_DIR, "old_pictures", name.strip())
        os.makedirs(archive_dir, exist_ok=True)
        dst = os.path.join(
            archive_dir, f"{int(time.time() * 1000)}_{os.path.basename(oldest.photo_path)}"
        )
        shutil.copy2(oldest.photo_path, dst)
        return {
            "embedding_id": oldest.id, "archived_path": dst, "vector": oldest.vec,
            "quality": oldest.quality_score, "added_at": oldest.added_at,
            "source_unknown_id": oldest.source_unknown_id,
        }
    except Exception as e:
        logger.error("[actualization] snapshot_oldest failed: %s", e, exc_info=True)
        return None


def finalize_old_picture(db, info):
    """promote_to_known ke BAAD call karo. Agar wo photo sach mein FIFO se hata
    to uska poora record (path + vector + quality) lauta deta hai, warna copy hata deta hai."""
    if not info:
        return None
    try:
        still_there = db.execute(
            text("SELECT 1 FROM face_embeddings WHERE id = :i"),
            {"i": info["embedding_id"]},
        ).first()
        if still_there:
            # kuch evict nahi hua: archive copy ki zaroorat nahi
            try:
                os.remove(info["archived_path"])
            except OSError:
                pass
            return None
        return info  # evict hua: archived_path + vector + quality + added_at
    except Exception as e:
        logger.error("[actualization] finalize_old_picture failed: %s", e, exc_info=True)
        return None
