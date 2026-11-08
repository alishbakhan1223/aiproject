"""
Alerts Router: Per-face crop alerts, unknown face listings, and detail views.

Endpoints:
- GET  /alerts/unknown-faces           (List unknown face alerts with filters: camera, zone, date, pagination)
- GET  /alerts/unknown-faces/{unknown_id}  (Detailed face alert record + sighting history + scene snapshot)
- POST /alerts/unknown-faces/{unknown_id}/promote (Promote unknown identity to registered known face)
"""
import os
import json
import re
from datetime import datetime, time as dtime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, and_

from app.database import get_db
from app.models import Event, UnknownPerson, UnknownSighting, User, KnownFace
from app.schemas import KnownFaceOut
from app.auth import get_current_user
from app.unknown_person_service import promote_to_known
from app.config import settings
from app.spec_actualization_service import (
    on_map, snapshot_oldest_before_promote, finalize_old_picture, check_mapping_window,
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


class UnknownFaceAlertItem(BaseModel):
    unknown_id: str
    raw_unknown_id: int
    camera_code: str
    zone: str  # "inside" | "outside"
    confidence: float
    confidence_percent: int
    face_image_url: Optional[str] = None
    scene_image_url: Optional[str] = None
    bounding_box: Optional[list[int]] = None
    timestamp: datetime
    event_id: Optional[int] = None
    sighting_id: Optional[int] = None

    class Config:
        from_attributes = True


class SightingDetailItem(BaseModel):
    id: int
    camera_code: str
    face_image_url: Optional[str] = None
    scene_image_url: Optional[str] = None
    bounding_box: Optional[list[int]] = None
    quality_score: Optional[float] = None
    timestamp: Optional[datetime] = None


class UnknownFaceDetailResponse(BaseModel):
    unknown_id: str
    raw_unknown_id: int
    camera_code: str
    zone: str
    confidence: float
    confidence_percent: int
    face_image_url: Optional[str] = None
    scene_image_url: Optional[str] = None
    bounding_box: Optional[list[int]] = None
    timestamp: datetime
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    status: str
    detection_count: int
    sightings: list[SightingDetailItem] = []


class PromoteRequest(BaseModel):
    name: Optional[str] = None
    known_face_id: Optional[int] = None
    company: Optional[str] = None
    branch: Optional[str] = None
    role: Optional[str] = None


def _format_snapshot_url(path: str | None) -> str | None:
    if not path:
        return None
    normalized = path.replace("\\", "/")
    marker = "data/snapshots/"
    idx = normalized.find(marker)
    rel = normalized[idx + len(marker):] if idx >= 0 else os.path.basename(normalized)
    encoded = "/".join(rel.split("/"))
    return f"/snapshots/{encoded}"


def _parse_raw_unknown_id(unknown_id_str: str | int) -> int:
    if isinstance(unknown_id_str, int):
        return unknown_id_str
    s = str(unknown_id_str).strip()
    match = re.search(r"(\d+)", s)
    if match:
        return int(match.group(1))
    raise HTTPException(status_code=400, detail=f"Invalid unknown ID format: {unknown_id_str}")


def _parse_bbox(bbox_raw) -> list[int] | None:
    if not bbox_raw:
        return None
    if isinstance(bbox_raw, list):
        return [int(v) for v in bbox_raw]
    if isinstance(bbox_raw, str):
        try:
            val = json.loads(bbox_raw)
            if isinstance(val, list):
                return [int(v) for v in val]
        except Exception:
            parts = [p.strip() for p in bbox_raw.split(",") if p.strip()]
            if len(parts) == 4:
                return [int(float(p)) for p in parts]
    return None


@router.get("/unknown-faces", response_model=list[UnknownFaceAlertItem])
def list_unknown_face_alerts(
    camera: Optional[str] = Query(None, description="Filter by camera name/code"),
    zone: Optional[str] = Query(None, description="Filter by zone: 'inside' or 'outside'"),
    date: Optional[str] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    limit: int = Query(50, le=500),
    page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """
    Returns list of unknown face alerts, newest first.
    Filters: camera, zone, date, pagination.
    """
    offset = (page - 1) * limit

    # Query from events table for unknown_person events (within 30 days)
    cutoff_30d = datetime.utcnow() - timedelta(days=getattr(settings, "MAPPING_WINDOW_DAYS", 30))
    query = db.query(Event).filter(
        Event.event_type == "unknown_person",
        Event.timestamp >= cutoff_30d,
    )

    if camera:
        query = query.filter(Event.camera_name.ilike(f"%{camera.strip()}%"))

    if zone:
        z = zone.strip().lower()
        if z == "inside":
            query = query.filter(Event.in_zone == True)
        elif z == "outside":
            query = query.filter(Event.in_zone == False)

    if date:
        try:
            target_date = datetime.strptime(date.strip(), "%Y-%m-%d").date()
            start_dt = datetime.combine(target_date, dtime.min)
            end_dt = datetime.combine(target_date, dtime.max)
            query = query.filter(and_(Event.timestamp >= start_dt, Event.timestamp <= end_dt))
        except ValueError:
            raise HTTPException(400, "Invalid date format. Expected YYYY-MM-DD")

    events = query.order_by(desc(Event.timestamp)).offset(offset).limit(limit).all()

    items = []
    for ev in events:
        raw_id = ev.unknown_person_id
        if not raw_id and ev.person_name:
            try:
                raw_id = _parse_raw_unknown_id(ev.person_name)
            except Exception:
                raw_id = ev.id

        formatted_id = f"Unknown-{raw_id:03d}" if raw_id else (ev.person_name or f"Unknown-{ev.id:03d}")
        conf = float(ev.confidence) if ev.confidence is not None else 0.80
        conf_pct = int(round(conf * 100)) if conf <= 1.0 else int(round(conf))
        if conf > 1.0:
            conf = conf / 100.0

        # Prioritize face_crop_path, then snapshot_path
        face_path = ev.face_crop_path or ev.snapshot_path
        scene_path = ev.raw_snapshot_path or ev.snapshot_path
        bbox = _parse_bbox(ev.bounding_box)

        # Fallback to sighting if available and scene/bbox missing
        if raw_id and (not scene_path or not bbox):
            sighting = (
                db.query(UnknownSighting)
                .filter(UnknownSighting.unknown_person_id == raw_id)
                .order_by(desc(UnknownSighting.timestamp))
                .first()
            )
            if sighting:
                if not face_path:
                    face_path = sighting.snapshot_path
                if not scene_path or scene_path == face_path:
                    scene_path = sighting.scene_snapshot_path or sighting.snapshot_path
                if not bbox and sighting.bounding_box:
                    bbox = _parse_bbox(sighting.bounding_box)

        items.append(
            UnknownFaceAlertItem(
                unknown_id=formatted_id,
                raw_unknown_id=raw_id or 0,
                camera_code=ev.camera_name or "Camera 1",
                zone="inside" if ev.in_zone else "outside",
                confidence=round(conf, 2),
                confidence_percent=conf_pct,
                face_image_url=_format_snapshot_url(face_path),
                scene_image_url=_format_snapshot_url(scene_path),
                bounding_box=bbox,
                timestamp=ev.timestamp or datetime.utcnow(),
                event_id=ev.id,
                sighting_id=None,
            )
        )

    # If no events found, fallback to UnknownPerson / Sightings directly
    if not items and not camera and not zone and not date:
        unknowns = (
            db.query(UnknownPerson)
            .order_by(desc(UnknownPerson.last_seen))
            .offset(offset)
            .limit(limit)
            .all()
        )
        for u in unknowns:
            latest_sighting = (
                db.query(UnknownSighting)
                .filter(UnknownSighting.unknown_person_id == u.id)
                .order_by(desc(UnknownSighting.timestamp))
                .first()
            )
            face_p = latest_sighting.snapshot_path if latest_sighting else u.representative_snapshot_path
            scene_p = latest_sighting.scene_snapshot_path if latest_sighting else u.representative_snapshot_path
            bbox = _parse_bbox(latest_sighting.bounding_box) if latest_sighting else None
            cam = latest_sighting.camera_name if latest_sighting else "Camera 1"
            ts = latest_sighting.timestamp if latest_sighting else (u.last_seen or u.first_seen or datetime.utcnow())
            q_score = latest_sighting.quality_score if latest_sighting and latest_sighting.quality_score else 80.0
            conf = min(0.99, max(0.40, q_score / 100.0))

            items.append(
                UnknownFaceAlertItem(
                    unknown_id=f"Unknown-{u.id:03d}",
                    raw_unknown_id=u.id,
                    camera_code=cam,
                    zone="inside",
                    confidence=round(conf, 2),
                    confidence_percent=int(round(conf * 100)),
                    face_image_url=_format_snapshot_url(face_p),
                    scene_image_url=_format_snapshot_url(scene_p),
                    bounding_box=bbox,
                    timestamp=ts,
                    event_id=None,
                    sighting_id=latest_sighting.id if latest_sighting else None,
                )
            )

    return items


@router.get("/unknown-faces/{unknown_id}", response_model=UnknownFaceDetailResponse)
def get_unknown_face_detail(
    unknown_id: str,
    db: Session = Depends(get_db),
):
    """
    Returns full detail for a single unknown face identity, including
    enlarged face crop, scene snapshot, highlighted box, and sighting history.
    """
    raw_id = _parse_raw_unknown_id(unknown_id)
    person = db.query(UnknownPerson).filter(UnknownPerson.id == raw_id).first()

    latest_event = (
        db.query(Event)
        .filter(Event.unknown_person_id == raw_id)
        .order_by(desc(Event.timestamp))
        .first()
    )

    sightings = (
        db.query(UnknownSighting)
        .filter(UnknownSighting.unknown_person_id == raw_id)
        .order_by(desc(UnknownSighting.timestamp))
        .all()
    )

    if not person and not latest_event and not sightings:
        raise HTTPException(404, f"Unknown face alert '{unknown_id}' not found")

    cam_code = (
        latest_event.camera_name
        if latest_event
        else (sightings[0].camera_name if sightings else "Camera 1")
    )
    in_zone = latest_event.in_zone if latest_event else True
    ts = (
        latest_event.timestamp
        if latest_event
        else (sightings[0].timestamp if sightings else (person.last_seen if person else datetime.utcnow()))
    )

    face_p = (
        (latest_event.face_crop_path or latest_event.snapshot_path)
        if latest_event
        else (person.representative_snapshot_path if person else (sightings[0].snapshot_path if sightings else None))
    )
    scene_p = (
        (latest_event.raw_snapshot_path or latest_event.snapshot_path)
        if latest_event
        else (sightings[0].scene_snapshot_path if sightings else face_p)
    )
    bbox = _parse_bbox(latest_event.bounding_box if latest_event else (sightings[0].bounding_box if sightings else None))

    conf = (
        float(latest_event.confidence)
        if (latest_event and latest_event.confidence is not None)
        else 0.85
    )
    if conf > 1.0:
        conf = conf / 100.0
    conf_pct = int(round(conf * 100))

    sighting_items = []
    for s in sightings:
        sighting_items.append(
            SightingDetailItem(
                id=s.id,
                camera_code=s.camera_name,
                face_image_url=_format_snapshot_url(s.snapshot_path),
                scene_image_url=_format_snapshot_url(s.scene_snapshot_path or s.snapshot_path),
                bounding_box=_parse_bbox(s.bounding_box),
                quality_score=s.quality_score,
                timestamp=s.timestamp,
            )
        )

    return UnknownFaceDetailResponse(
        unknown_id=f"Unknown-{raw_id:03d}",
        raw_unknown_id=raw_id,
        camera_code=cam_code,
        zone="inside" if in_zone else "outside",
        confidence=round(conf, 2),
        confidence_percent=conf_pct,
        face_image_url=_format_snapshot_url(face_p),
        scene_image_url=_format_snapshot_url(scene_p),
        bounding_box=bbox,
        timestamp=ts,
        first_seen=person.first_seen if person else ts,
        last_seen=person.last_seen if person else ts,
        status=person.status if person else "active",
        detection_count=len(sightings),
        sightings=sighting_items,
    )


@router.post("/unknown-faces/{unknown_id}/promote", response_model=KnownFaceOut)
def promote_unknown_face(
    unknown_id: str,
    payload: PromoteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Promote unknown face identity to registered known face.
    """
    raw_id = _parse_raw_unknown_id(unknown_id)
    target_name = None
    if payload.known_face_id:
        kf = db.query(KnownFace).filter(KnownFace.id == payload.known_face_id).first()
        if not kf:
            raise HTTPException(404, "Selected known person not found")
        target_name = kf.name
    elif payload.name and payload.name.strip():
        target_name = payload.name.strip()
    else:
        raise HTTPException(400, "Person name is required for promotion")

    ok, msg = check_mapping_window(raw_id, db)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    fifo_info = snapshot_oldest_before_promote(db, target_name)
    try:
        known_face = promote_to_known(raw_id, target_name, db)
        if payload.company:
            known_face.company = payload.company.strip()
        if payload.branch:
            known_face.branch = payload.branch.strip()
        if payload.role:
            known_face.role = payload.role.strip()
        db.commit()
        db.refresh(known_face)
        # Spec: map hote hi actualization table mein entry
        old_info = finalize_old_picture(db, fifo_info)
        on_map(raw_id, user.username, known_face.id, old_info)
    except ValueError as e:
        raise HTTPException(404, str(e))

    result = KnownFaceOut.model_validate(known_face)
    result.photo_count = len(known_face.embeddings)
    return result