"""
Per-Face Crop and Multi-Person Scene Processing Service.

Responsibilities:
1. Extract high-quality, padded face crops per detected person (known and unknown) in multi-person scenes.
2. Save both individual face crops and scene snapshots into dedicated folders.
3. Manage per-track debounce/voting so stable tracks don't spam repeated duplicate events.
4. Provide clean data structures for Events / Alerts and Face Detail views.
"""
import os
import time
import json
import logging
import cv2
import numpy as np
from datetime import datetime
from sqlalchemy import text, select
from sqlalchemy.orm import Session

from app.models import UnknownPerson, UnknownEmbedding, UnknownSighting, Event
from app.config import settings
from app.face_quality import evaluate_face_quality, _variance_of_laplacian

logger = logging.getLogger(__name__)

_DEDUP_LOCK_KEY = 913_223_001
TRACK_DEBOUNCE_SECONDS = 4.0  # Min interval to emit duplicate alerts for the same track_id


def crop_face_with_padding(frame: np.ndarray, bbox, padding_pct: float = 0.20) -> np.ndarray:
    """
    Crops a face from `frame` using bounding box `(x1, y1, x2, y2)` with proportional padding.
    Maintains clean boundaries clamped to image dimensions.
    """
    if frame is None or frame.size == 0 or bbox is None:
        return None

    h_img, w_img = frame.shape[:2]
    x1, y1, x2, y2 = map(int, bbox)

    bw = max(1, x2 - x1)
    bh = max(1, y2 - y1)

    pad_x = int(bw * padding_pct)
    pad_y = int(bh * padding_pct)

    cx1 = max(0, x1 - pad_x)
    cy1 = max(0, y1 - pad_y)
    cx2 = min(w_img, x2 + pad_x)
    cy2 = min(h_img, y2 + pad_y)

    crop = frame[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        return None
    return crop


def _save_image_to(folder: str, prefix: str, camera_name: str, img: np.ndarray) -> str:
    """Saves image to folder using WebP (with JPEG fallback) and unique timestamp."""
    os.makedirs(folder, exist_ok=True)
    sanitized_cam = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in camera_name)
    ts = int(time.time() * 1000)
    filename = f"{prefix}_{sanitized_cam}_{ts}.webp"
    path = f"{folder}/{filename}"

    success = cv2.imwrite(path, img, [cv2.IMWRITE_WEBP_QUALITY, 90])
    if not success:
        filename = f"{prefix}_{sanitized_cam}_{ts}.jpg"
        path = f"{folder}/{filename}"
        cv2.imwrite(path, img)
    return path


def _cosine_dist(vec_a: np.ndarray, vec_b) -> float:
    stored = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(stored)
    if norm_a == 0 or norm_b == 0:
        return 1.0
    cos_sim = float(np.dot(vec_a, stored) / (norm_a * norm_b + 1e-8))
    return float(1.0 - cos_sim)


class TrackAlertManager:
    """Tracks per-track alert cooldowns to avoid duplicate flood while tracking."""
    def __init__(self, debounce_seconds: float = TRACK_DEBOUNCE_SECONDS):
        self.debounce_seconds = debounce_seconds
        self._last_alert_time: dict[tuple[str, int], float] = {}  # (camera_name, track_id) -> timestamp
        self._track_identities: dict[tuple[str, int], int] = {}  # (camera_name, track_id) -> unknown_person_id

    def should_emit_alert(self, camera_name: str, track_id: int | None, unknown_person_id: int) -> bool:
        if track_id is None:
            return True
        key = (camera_name, track_id)
        now = time.time()
        last_t = self._last_alert_time.get(key, 0.0)
        last_id = self._track_identities.get(key)

        if (now - last_t) >= self.debounce_seconds or last_id != unknown_person_id:
            self._last_alert_time[key] = now
            self._track_identities[key] = unknown_person_id
            return True
        return False


track_alert_manager = TrackAlertManager()


def process_known_face_crop(
    face,
    frame: np.ndarray,
    camera_name: str,
    person_name: str,
    is_in_zone: bool = True,
    track_id: int = None,
) -> dict | None:
    """
    Crops known person's face with padding and saves both face crop and scene snapshot
    under data/snapshots/known/<person_name>/.
    """
    if frame is None or face is None:
        return None

    bbox_coords = list(map(int, face.bbox)) if hasattr(face, "bbox") else None
    if not bbox_coords:
        return None

    face_crop = crop_face_with_padding(frame, bbox_coords, padding_pct=0.20)
    if face_crop is None:
        face_crop = frame

    sanitized_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (person_name or "known"))
    identity_folder = f"{settings.SNAPSHOT_DIR}/known/{sanitized_name}"
    os.makedirs(identity_folder, exist_ok=True)

    crop_path = _save_image_to(identity_folder, "crop", camera_name, face_crop)
    scene_path = _save_image_to(identity_folder, "scene", camera_name, frame)

    bbox_json = json.dumps(bbox_coords)

    return {
        "person_name": person_name,
        "camera_name": camera_name,
        "face_crop_path": crop_path,
        "scene_snapshot_path": scene_path,
        "bounding_box": bbox_coords,
        "bounding_box_json": bbox_json,
        "in_zone": is_in_zone,
        "track_id": track_id,
        "timestamp": datetime.utcnow(),
    }


def process_unknown_face_alert(
    face,
    frame: np.ndarray,
    camera_name: str,
    db: Session,
    is_in_zone: bool = True,
    track_id: int = None,
    exclude_person_ids: set[int] = None,
) -> dict | None:
    """
    Core pipeline function for unknown face processing:
    1. Quality assessment & skip non-acceptable faces.
    2. Crop face per person with padding.
    3. Match or create UnknownPerson (excluding `exclude_person_ids` in same frame).
    4. Save individual face crop & full scene snapshot into person's dedicated folder.
    5. Save UnknownSighting and UnknownEmbedding.
    6. Return complete metadata dictionary for event dispatch and alerts view.
    """
    if frame is None or face is None:
        return None

    # Quality check
    quality = getattr(face, "quality_info", None) or evaluate_face_quality(frame, face)
    if not quality.get("is_acceptable", False):
        logger.debug(
            "[%s] Face rejected by quality gate: %s",
            camera_name, quality.get("rejection_reason"),
        )
        return None

    quality_score = float(quality.get("quality_score", 50.0))
    det_score = float(getattr(face, "det_score", 0.90))

    bbox_coords = list(map(int, face.bbox))
    face_crop = crop_face_with_padding(frame, bbox_coords, padding_pct=0.20)
    if face_crop is None:
        return None

    now = datetime.utcnow()
    embedding = face.embedding

    # Advisory lock to ensure thread safety across camera workers
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _DEDUP_LOCK_KEY})

    # Find nearest matching unknown candidate
    stmt_emb = select(UnknownEmbedding)
    if exclude_person_ids:
        stmt_emb = stmt_emb.filter(UnknownEmbedding.unknown_person_id.notin_(exclude_person_ids))
    row_emb = db.execute(
        stmt_emb.order_by(UnknownEmbedding.vector.cosine_distance(embedding)).limit(1)
    ).scalars().first()

    pid_a, dist_a = (row_emb.unknown_person_id, _cosine_dist(embedding, row_emb.vector)) if row_emb else (None, None)

    stmt_ref = select(UnknownPerson)
    if exclude_person_ids:
        stmt_ref = stmt_ref.filter(UnknownPerson.id.notin_(exclude_person_ids))
    row_ref = db.execute(
        stmt_ref.order_by(UnknownPerson.reference_embedding.cosine_distance(embedding)).limit(1)
    ).scalars().first()

    pid_b, dist_b = (row_ref.id, _cosine_dist(embedding, row_ref.reference_embedding)) if row_ref else (None, None)

    best_pid, best_dist = None, None
    for pid, dist in ((pid_a, dist_a), (pid_b, dist_b)):
        if pid is not None and (best_dist is None or dist < best_dist):
            best_pid, best_dist = pid, dist

    matched_person = None
    if best_pid is not None and best_dist <= settings.UNKNOWN_PERSON_DISTANCE_THRESHOLD:
        matched_person = db.query(UnknownPerson).filter(UnknownPerson.id == best_pid).first()

    is_new = False
    if matched_person is None:
        is_new = True
        matched_person = UnknownPerson(
            reference_embedding=embedding,
            first_seen=now,
            last_seen=now,
            status="active",
        )
        db.add(matched_person)
        db.flush()

    identity_folder = f"{settings.SNAPSHOT_DIR}/unknown/Unknown-{matched_person.id:03d}"
    os.makedirs(identity_folder, exist_ok=True)

    # Save per-face crop
    crop_path = _save_image_to(identity_folder, "crop", camera_name, face_crop)
    # Save full scene snapshot
    scene_path = _save_image_to(identity_folder, "scene", camera_name, frame)

    matched_person.last_seen = now
    matched_person.status = "active"

    # Maintain highest quality crop as representative snapshot
    if is_new or not matched_person.representative_snapshot_path:
        matched_person.representative_snapshot_path = crop_path
    else:
        # Check if current crop is higher quality
        best_existing = (
            db.query(UnknownSighting)
            .filter(UnknownSighting.unknown_person_id == matched_person.id)
            .order_by(UnknownSighting.quality_score.desc().nullslast())
            .first()
        )
        prev_best = best_existing.quality_score if best_existing and best_existing.quality_score is not None else -1.0
        if quality_score >= prev_best:
            matched_person.representative_snapshot_path = crop_path

    bbox_json = json.dumps(bbox_coords)

    db.add(
        UnknownSighting(
            unknown_person_id=matched_person.id,
            camera_name=camera_name,
            snapshot_path=crop_path,
            scene_snapshot_path=scene_path,
            bounding_box=bbox_json,
            quality_score=quality_score,
            timestamp=now,
        )
    )
    db.add(
        UnknownEmbedding(
            unknown_person_id=matched_person.id,
            vector=embedding,
            snapshot_path=crop_path,
            quality_score=quality_score,
            created_at=now,
        )
    )
    db.commit()
    db.refresh(matched_person)

    formatted_id = f"Unknown-{matched_person.id:03d}"
    confidence_val = round(det_score, 2)

    return {
        "unknown_person": matched_person,
        "is_new": is_new,
        "unknown_id": formatted_id,
        "raw_unknown_id": matched_person.id,
        "camera_name": camera_name,
        "face_crop_path": crop_path,
        "scene_snapshot_path": scene_path,
        "bounding_box": bbox_coords,
        "bounding_box_json": bbox_json,
        "quality_score": quality_score,
        "confidence": confidence_val,
        "in_zone": is_in_zone,
        "track_id": track_id,
        "timestamp": now,
    }
