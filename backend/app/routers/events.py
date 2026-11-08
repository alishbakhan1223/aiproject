from datetime import datetime

import cv2
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import User, Event, KnownFace, FaceEmbedding
from app.schemas import EventOut, ConfirmKnownIn
from app.face_engine import extract_faces
from app.auth import get_current_user

router = APIRouter(tags=["Events"])

# Max reference face images stored per registered person (spec Section 1 & 7)
MAX_FACE_IMAGES = 4


@router.get("/events", response_model=list[EventOut])
def get_events(
    limit: int = Query(50, le=500),
    event_type: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Event).order_by(desc(Event.timestamp))
    if event_type:
        q = q.filter(Event.event_type == event_type)
    return q.limit(limit).all()


@router.get("/alerts", response_model=list[EventOut])
def get_alerts(limit: int = Query(50, le=500), db: Session = Depends(get_db)):
    """Alerts = unknown persons + restricted objects + forensic confirmations + weapon detections."""
    return (
        db.query(Event)
        .filter(Event.event_type.in_(
            ["unknown_person", "restricted_object", "forensic_confirmation", "weapon_detected"]
        ))
        .order_by(desc(Event.timestamp))
        .limit(limit)
        .all()
    )


@router.post("/events/{event_id}/confirm-known", response_model=EventOut)
def confirm_known_person(
    event_id: int,
    payload: ConfirmKnownIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    "Make Known" action (spec Sections 5-9).

    Links an Unknown-person Event to an existing registered KnownFace, and
    folds the Unknown snapshot into that person's reference-image set with
    a FIFO cap of MAX_FACE_IMAGES images (oldest dropped by added_at once
    the cap is hit). The original Unknown Event row and snapshot are never
    deleted — only its status/link fields are updated, preserving the
    audit trail required by the spec.
    """
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "Event not found")
    if not event.is_unknown:
        raise HTTPException(400, "Event is not an unknown-person event")

    known_face = db.query(KnownFace).filter(KnownFace.id == payload.known_face_id).first()
    if not known_face:
        raise HTTPException(404, "Known person not found")

    # Try to fold the unknown snapshot into this person's reference-image set
    if event.snapshot_path:
        frame = cv2.imread(event.snapshot_path)
        faces = extract_faces(frame) if frame is not None else []
        if faces:
            existing = (
                db.query(FaceEmbedding)
                .filter(FaceEmbedding.face_id == known_face.id)
                .order_by(FaceEmbedding.added_at.asc())
                .all()
            )
            if len(existing) >= MAX_FACE_IMAGES:
                oldest = existing[0]  # FIFO: oldest by added_at timestamp, not filename
                db.delete(oldest)
                db.flush()
            db.add(FaceEmbedding(
                face_id=known_face.id,
                vector=faces[0].embedding.tolist(),
                photo_path=event.snapshot_path,
                added_at=datetime.utcnow(),
            ))

    event.is_unknown = False
    event.person_name = known_face.name
    event.known_face_id = known_face.id
    event.confirmed_by = user.username if hasattr(user, "username") else str(user)
    event.confirmed_at = datetime.utcnow()

    db.commit()
    db.refresh(event)
    return event
