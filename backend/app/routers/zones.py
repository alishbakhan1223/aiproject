"""
Zone-based trespass alerting: an admin draws a polygon on a camera's live
feed in the frontend Zone Editor; only detections whose bounding-box center
falls inside that polygon trigger unknown-person / restricted-object alerts.
Cameras without a saved zone fall back to treating the whole frame as the zone.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User,  Zone
from app.schemas import ZoneIn, ZoneOut
from app.auth import get_current_user
from app.camera_worker import refresh_zone

router = APIRouter(prefix="/zones", tags=["Zones"])


@router.get("/{camera_id}", response_model=ZoneOut | None)
def get_zone(camera_id: int, db: Session = Depends(get_db)):
    zone = db.query(Zone).filter(Zone.camera_id == camera_id).first()
    if not zone:
        return None
    return ZoneOut(camera_id=camera_id, points=json.loads(zone.polygon))


@router.post("", response_model=ZoneOut)
def save_zone(payload: ZoneIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if len(payload.points) < 3:
        raise HTTPException(400, "A zone polygon needs at least 3 points")

    zone = db.query(Zone).filter(Zone.camera_id == payload.camera_id).first()
    polygon_json = json.dumps(payload.points)
    if zone:
        zone.polygon = polygon_json
    else:
        zone = Zone(camera_id=payload.camera_id, polygon=polygon_json)
        db.add(zone)
    db.commit()

    refresh_zone(payload.camera_id)  # live-update a running camera worker, if any
    return ZoneOut(camera_id=payload.camera_id, points=payload.points)


@router.delete("/{camera_id}")
def delete_zone(camera_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    zone = db.query(Zone).filter(Zone.camera_id == camera_id).first()
    if zone:
        db.delete(zone)
        db.commit()
        refresh_zone(camera_id)
    return {"status": "deleted", "camera_id": camera_id}

