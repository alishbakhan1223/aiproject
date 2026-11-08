from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event, KnownFace, Camera
from app.schemas import StatisticsOut

router = APIRouter(tags=["Statistics"])


@router.get("/statistics", response_model=StatisticsOut)
def get_statistics(db: Session = Depends(get_db)):
    total = db.query(Event).count()
    unknown = db.query(Event).filter(Event.event_type == "unknown_person").count()
    restricted = db.query(Event).filter(Event.event_type == "restricted_object").count()
    weapon = db.query(Event).filter(Event.event_type == "weapon_detected").count()
    known = db.query(Event).filter(Event.event_type == "known_person").count()
    forensic = db.query(Event).filter(Event.event_type == "forensic_confirmation").count()
    faces = db.query(KnownFace).count()
    active_cams = db.query(Camera).filter(Camera.is_active == True).count()  # noqa: E712

    return StatisticsOut(
        total_events=total,
        unknown_person_events=unknown,
        restricted_object_events=restricted,
        weapon_events=weapon,
        known_person_events=known,
        forensic_confirmations=forensic,
        total_known_faces=faces,
        active_cameras=active_cams,
    )
