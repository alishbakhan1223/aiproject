"""
Naya unknown insaan milne par smart ID banata hai:
UNKN + company + location + camera + date(MMDDYY) + number(3 digit)
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.database import SessionLocal

logger = logging.getLogger(__name__)

PKT = timezone(timedelta(hours=5))  # Pakistan time (UTC+5)

_done_ids = set()         # jin unknown_persons ki smart ID ban chuki (dobara DB nahi dekhna)
_warned_cameras = set()   # jis camera ka warning ek baar de diya


def register_spec_unknown(unknown_person_id: int, camera_id: int):
    """Returns unknown_id, ya None (skip / duplicate). Kabhi error bahar nahi phenkta."""
    if unknown_person_id in _done_ids:
        return None
    db = SessionLocal()
    try:
        # 1) Camera ka code aur location chahiye
        cam = db.execute(
            text("SELECT camera_code, camera_location FROM cameras WHERE id = :cid"),
            {"cid": camera_id},
        ).first()
        if not cam or not cam.camera_code or not cam.camera_location:
            if camera_id not in _warned_cameras:
                _warned_cameras.add(camera_id)
                logger.warning("[spec_unknowns] camera id=%s ka camera_code/location set nahi - skip", camera_id)
            return None

        # 2) Company code (.env mein DEFAULT_COMPANY_CODE, warna companies ki pehli row)
        company_code = os.getenv("DEFAULT_COMPANY_CODE")
        if not company_code:
            row = db.execute(text("SELECT company_code FROM companies ORDER BY company_code LIMIT 1")).first()
            company_code = row.company_code if row else None
        if not company_code:
            logger.warning("[spec_unknowns] companies table khali hai - skip")
            return None

        # 3) Insight ID = face system ka ID (yahan: unknown_persons.id)
        insight_id = f"unknown-person-{unknown_person_id}"

        # 4) Aaj ki date, Pakistan time mein (ID aur date_time dono isi se bante hain)
        now = datetime.now(PKT).replace(tzinfo=None)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        # 5) Ek camera + ek din ke liye lock (do threads same number na banayein)
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
            {"k": f"spec-unknown-{cam.camera_code}-{day_start.date()}"},
        )

        # 6) Duplicate check
        if db.execute(text("SELECT 1 FROM unknowns WHERE insight_id = :i"), {"i": insight_id}).first():
            _done_ids.add(unknown_person_id)
            return None

        # 7) Aaj is camera ka sabse bada number + 1
        #    (COUNT nahi: delete ke baad number purani ID se na takraye)
        number = db.execute(
            text(
                "SELECT COALESCE(MAX(unknown_creation_number), 0) + 1 FROM unknowns "
                "WHERE camera_code = :c AND date_time >= :s AND date_time < :e"
            ),
            {"c": cam.camera_code, "s": day_start, "e": day_end},
        ).scalar()

        # 8) Smart ID: date MMDDYY (bina dash)
        unknown_id = (
            f"UNKN{company_code}{cam.camera_location}{cam.camera_code}"
            f"{now.strftime('%m%d%y')}{number:03d}"
        )

        db.execute(
            text(
                "INSERT INTO unknowns (unknown_id, company_code, location_code, camera_code, "
                "insight_id, date_time, unknown_creation_number) "
                "VALUES (:uid, :co, :loc, :cam, :ins, :dt, :num) ON CONFLICT DO NOTHING"
            ),
            {"uid": unknown_id, "co": company_code, "loc": cam.camera_location,
             "cam": cam.camera_code, "ins": insight_id, "dt": now, "num": number},
        )
        db.commit()
        _done_ids.add(unknown_person_id)
        logger.info("[spec_unknowns] created %s", unknown_id)
        return unknown_id
    except Exception as e:
        db.rollback()
        logger.error("[spec_unknowns] failed: %s", e, exc_info=True)
        return None
    finally:
        db.close()