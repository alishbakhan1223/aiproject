"""
Read + convert endpoints for unknown persons.
"""
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.database import get_db
from typing import Optional
from app.models import UnknownPerson, UnknownSighting, User, KnownFace
from app.schemas import UnknownPersonOut, UnknownSightingOut, KnownFaceOut
from app.unknown_person_service import promote_to_known, revert_to_unknown, split_sighting_to_new_unknown
from app.auth import get_current_user, require_admin
from app.config import settings
from app.spec_actualization_service import (
    on_map, on_delete, on_undo_known,
    snapshot_oldest_before_promote, finalize_old_picture,
    check_mapping_window, check_revert_lock_for_known_face, PKT,
)
from datetime import datetime, timedelta
from sqlalchemy import text

router = APIRouter(tags=["Unknown Persons"])


class ConvertToKnownRequest(BaseModel):
    name: Optional[str] = None
    known_face_id: Optional[int] = None


@router.get("/unknown-persons", response_model=list[UnknownPersonOut])
def list_unknown_persons(
    limit: int = Query(50, le=500),
    status: str = Query("active"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One row per distinct unknown individual, most recently seen first.
    `status` defaults to "active" so deactualized (left-camera-view)
    identities don't clutter the live list — pass status=inactive or
    status=all to see everything (nothing is ever deleted)."""
    if status not in ("active", "inactive", "all"):
        raise HTTPException(400, "status must be one of: active, inactive, all")

    query = (
        db.query(UnknownPerson, func.count(UnknownSighting.id).label("detection_count"))
        .outerjoin(UnknownSighting, UnknownSighting.unknown_person_id == UnknownPerson.id)
    )
    if status != "all":
        query = query.filter(UnknownPerson.status == status)

    rows = (
        query.group_by(UnknownPerson.id)
        .order_by(desc(UnknownPerson.last_seen))
        .limit(limit)
        .all()
    )
    now = datetime.now(PKT).replace(tzinfo=None)
    allowed_days = getattr(settings, "MAPPING_WINDOW_DAYS", 30)
    results = []
    for person, count in rows:
        # Determine base detection time
        u_row = db.execute(
            text("SELECT unknown_id, date_time FROM unknowns WHERE insight_id = :i"),
            {"i": f"unknown-person-{person.id}"},
        ).first()
        # Determine base detection time (convert UTC first_seen to PKT by adding 5 hours)
        if u_row and u_row.date_time:
            det_time = u_row.date_time
        elif person.first_seen:
            det_time = person.first_seen + timedelta(hours=5)
        else:
            det_time = now

        has_act = False
        if u_row:
            has_act = bool(db.execute(
                text("SELECT 1 FROM actualization WHERE unkn_id = :u"),
                {"u": u_row.unknown_id},
            ).first())

        elapsed_days = (now - det_time).total_seconds() / 86400.0 if det_time else 0.0
        # Filter out if older than 30 days and never mapped
        if elapsed_days > allowed_days and not has_act:
            continue

        item = UnknownPersonOut.model_validate(person)
        item.detection_count = count or 0
        item.mapping_days_left = max(0, int(allowed_days - elapsed_days))
        results.append(item)
    return results


@router.get("/unknown-persons/{unknown_person_id}", response_model=UnknownPersonOut)
def get_unknown_person(
    unknown_person_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    person = db.query(UnknownPerson).filter(UnknownPerson.id == unknown_person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Unknown person not found")
    count = (
        db.query(func.count(UnknownSighting.id))
        .filter(UnknownSighting.unknown_person_id == unknown_person_id)
        .scalar()
    )
    u_row = db.execute(
        text("SELECT unknown_id, date_time FROM unknowns WHERE insight_id = :i"),
        {"i": f"unknown-person-{person.id}"},
    ).first()
    now = datetime.now(PKT).replace(tzinfo=None)
    allowed_days = getattr(settings, "MAPPING_WINDOW_DAYS", 30)
    if u_row and u_row.date_time:
        det_time = u_row.date_time
    elif person.first_seen:
        det_time = person.first_seen + timedelta(hours=5)
    else:
        det_time = now
    elapsed_days = (now - det_time).total_seconds() / 86400.0 if det_time else 0.0

    item = UnknownPersonOut.model_validate(person)
    item.detection_count = count or 0
    item.mapping_days_left = max(0, int(allowed_days - elapsed_days))
    return item


@router.get(
    "/unknown-persons/{unknown_person_id}/sightings",
    response_model=list[UnknownSightingOut],
)
def list_unknown_person_sightings(
    unknown_person_id: int,
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    person = db.query(UnknownPerson).filter(UnknownPerson.id == unknown_person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Unknown person not found")
    sightings = (
        db.query(UnknownSighting)
        .filter(UnknownSighting.unknown_person_id == unknown_person_id)
        .order_by(desc(UnknownSighting.timestamp))
        .limit(limit)
        .all()
    )
    return [UnknownSightingOut.model_validate(s) for s in sightings]


@router.post(
    "/unknown-persons/{unknown_person_id}/sightings/{sighting_id}/remove",
    response_model=UnknownPersonOut,
)
def remove_sighting_to_new_identity(
    unknown_person_id: int,
    sighting_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Additional Unknowns Management: a single sighting was wrongly
    grouped into this Unknown-NNN identity (e.g. two different people
    got merged together). Pulls it out into its own new, separate
    unknown identity — nothing is deleted."""
    sighting = db.query(UnknownSighting).filter(
        UnknownSighting.id == sighting_id,
        UnknownSighting.unknown_person_id == unknown_person_id,
    ).first()
    if not sighting:
        raise HTTPException(404, "Sighting not found under this unknown person")

    try:
        new_person = split_sighting_to_new_unknown(sighting_id, db)
    except ValueError:
        raise HTTPException(404, "Sighting not found")

    item = UnknownPersonOut.model_validate(new_person)
    item.detection_count = len(new_person.sightings)
    return item


@router.post("/unknown-persons/{unknown_person_id}/convert-to-known", response_model=KnownFaceOut)
def convert_to_known(
    unknown_person_id: int,
    payload: ConvertToKnownRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Converts an unknown_person into a named known_face."""
    target_name = None
    if payload.known_face_id:
        kf = db.query(KnownFace).filter(KnownFace.id == payload.known_face_id).first()
        if not kf:
            raise HTTPException(404, "Selected known person not found")
        target_name = kf.name
    elif payload.name and payload.name.strip():
        target_name = payload.name.strip()
    else:
        raise HTTPException(400, "Name or known_face_id is required")

    ok, msg = check_mapping_window(unknown_person_id, db)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # FIFO: slots bhare hon to sabse purani photo ki copy pehle rakh lo
    fifo_info = snapshot_oldest_before_promote(db, target_name)
    try:
        known_face = promote_to_known(unknown_person_id, target_name, db)
    except ValueError:
        raise HTTPException(404, "Unknown person not found")

    # Spec: map hote hi actualization table mein entry (+ FIFO se hatayi gayi purani picture)
    old_info = finalize_old_picture(db, fifo_info)
    on_map(unknown_person_id, user.username, known_face.id, old_info)

    result = KnownFaceOut.model_validate(known_face)
    result.photo_count = len(known_face.embeddings)
    return result


@router.delete("/unknown-persons/{unknown_person_id}")
def delete_unknown_person(
    unknown_person_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Delete an unknown person and all associated embeddings/sightings (Admin only)."""
    person = db.query(UnknownPerson).filter(UnknownPerson.id == unknown_person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Unknown person not found")

    unknown_dir = os.path.join(
        settings.SNAPSHOT_DIR, "unknown", f"Unknown-{person.id:03d}"
    )
    if os.path.isdir(unknown_dir):
        shutil.rmtree(unknown_dir, ignore_errors=True)

    db.delete(person)
    db.commit()

    # Spec: unknowns table se bhi row hatao (actualization pehle, phir unknowns)
    on_delete(unknown_person_id)

    return {"status": "deleted", "id": unknown_person_id}


@router.post("/known-faces/{known_face_id}/revert-to-unknown", response_model=UnknownPersonOut)
def revert_known_to_unknown(
    known_face_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Additional Unknowns Management: undo a mistaken known-face
    registration/promotion. History (Events, photos) is preserved —
    nothing is deleted, the identity just moves back into the unknown pool."""
    is_locked, locked_photos, _ = check_revert_lock_for_known_face(db, known_face_id)
    if is_locked:
        raise HTTPException(
            status_code=403,
            detail=f"Revert window (48 hours) closed. Changes are not allowed anymore. Locked photo IDs: {locked_photos}",
        )

    try:
        unknown_person = revert_to_unknown(known_face_id, db)
    except ValueError:
        raise HTTPException(404, "Known face not found")

    # Spec: undo par actualization se entry hatao (unknown wahi ID par wapas)
    on_undo_known(known_face_id)

    item = UnknownPersonOut.model_validate(unknown_person)
    item.detection_count = len(unknown_person.sightings)
    return item