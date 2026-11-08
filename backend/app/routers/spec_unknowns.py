"""
Frontend ke liye: unknowns ki list (location aur date filter ke saath).
Date in MM-DD-YY format (e.g. 10-06-26).
Business Rules:
- 30-day mapping window: unmapped unknowns > 30d filtered out.
- "Map within" column: shows remaining days (or Mapped).
- Status rule:
  - Mapped: Successful (agar <=48h mein map hua), Unsuccessful (agar >48h mein map hua).
  - Unmapped: Pending (48 ghante tak), Unsuccessful (48 ghante ke baad).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/spec-unknowns", tags=["Spec Unknowns"])
PKT = timezone(timedelta(hours=5))


@router.get("/locations")
def list_locations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.execute(text("SELECT location_code, location_name FROM locations ORDER BY location_code")).all()
    return [{"location_code": r.location_code, "location_name": r.location_name} for r in rows]


@router.get("")
def list_spec_unknowns(
    location_code: Optional[str] = Query(None),
    date: Optional[str] = Query(None, description="MM-DD-YY, for example 10-06-26"),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    now = datetime.now(PKT).replace(tzinfo=None)
    allowed_days = getattr(settings, "MAPPING_WINDOW_DAYS", 30)
    revert_window_hours = getattr(settings, "REVERT_WINDOW_HOURS", 48.0)
    cutoff_30d = now - timedelta(days=allowed_days)

    where, params = [], {"limit": limit, "cutoff_30d": cutoff_30d}

    # Rule 2: 30 din se purane unmapped unknowns ko foran filter kar do
    where.append("(EXISTS (SELECT 1 FROM actualization a WHERE a.unkn_id = r.unknown_id) OR r.detected_at >= :cutoff_30d)")

    if location_code:
        where.append("r.location_code = :loc")
        params["loc"] = location_code
    if date:
        try:
            params["d"] = datetime.strptime(date, "%m-%d-%y").date()
        except ValueError:
            raise HTTPException(400, "Date must be in MM-DD-YY format (for example 10-06-26)")
        where.append("r.detected_at::date = :d")

    sql = f"""
        SELECT r.unknown_id, r.company_name, r.location_code, r.location_name, r.camera_code,
               r.date_shown, r.time_shown, r.detected_at,
               (SELECT a.status FROM actualization a
                 WHERE a.unkn_id = r.unknown_id ORDER BY a.time_stamp DESC LIMIT 1) AS actualization_status
        FROM unknowns_report r
        {"WHERE " + " AND ".join(where) if where else ""}
        ORDER BY r.detected_at DESC
        LIMIT :limit
    """
    rows = db.execute(text(sql), params).mappings().all()

    results = []
    for r in rows:
        item = dict(r)
        detected_at = item.get("detected_at")
        act_status = item.get("actualization_status")

        if act_status:
            # Mapped unknown: actualization status use karo
            item["status"] = act_status
            item["map_within"] = "Mapped"
            item["mapping_days_left"] = None
        else:
            # Unmapped unknown:
            # 48 ghante tak Pending, phir Unsuccessful
            elapsed_hours = (now - detected_at).total_seconds() / 3600.0 if detected_at else 0.0
            if elapsed_hours <= revert_window_hours:
                item["status"] = "Pending"
            else:
                item["status"] = "Unsuccessful"

            elapsed_days = elapsed_hours / 24.0
            days_left = max(0, int(allowed_days - elapsed_days))
            item["mapping_days_left"] = days_left
            item["map_within"] = f"{days_left} days left" if days_left > 0 else "Expired"

        results.append(item)

    return results
