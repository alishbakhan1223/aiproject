"""
Face recognition wrapper around InsightFace.
Handles: embedding extraction + quality gating + matching against known faces stored in pgvector.
"""
import logging
import cv2
import numpy as np
from insightface.app import FaceAnalysis
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import FaceEmbedding, KnownFace
from app.config import settings
from app.face_quality import evaluate_face_quality

logger = logging.getLogger(__name__)

# 'buffalo_l' is a free, pre-trained InsightFace model bundle (downloads on first run)
_face_app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
_face_app.prepare(ctx_id=0, det_size=(640, 640))


def is_strict_frontal_face(face, frame: np.ndarray = None) -> bool:
    """
    Strict gate applied to every face before it's used for registration or matching.
    Rejects blurry, low-confidence, tiny, and non-frontal faces.
    """
    quality = evaluate_face_quality(frame, face)
    return quality["is_acceptable"]


# Alias kept for backwards-compatibility
is_frontal_face = is_strict_frontal_face


def extract_faces(frame: np.ndarray):
    """
    Returns list of insightface Face objects detected in a BGR frame,
    filtered down to only clear, sharp, strictly front-facing faces that pass quality gating.
    Attaches .quality_info dict (including quality_score) to each returned face.
    """
    if frame is None:
        return []

    raw_faces = _face_app.get(frame)
    accepted = []
    for face in raw_faces:
        quality = evaluate_face_quality(frame, face)
        face.quality_info = quality
        if quality["is_acceptable"]:
            accepted.append(face)
        else:
            logger.debug(
                "Rejected face: bbox=%s reason=%s quality_score=%s",
                face.bbox, quality.get("rejection_reason"), quality.get("quality_score"),
            )
    return accepted


def match_face(embedding: np.ndarray, db: Session):
    """
    Compares an embedding against all known face embeddings using cosine distance
    via pgvector's <=> operator. Returns (name, distance, face_id, photo_path)
    or (None, None, None, None) if no match. photo_path lets the live camera
    loop reuse the person's existing reference photo for dashboard display.
    """
    result = db.execute(
        select(FaceEmbedding, KnownFace.name, KnownFace.id, KnownFace.photo_path)
        .join(KnownFace, FaceEmbedding.face_id == KnownFace.id)
        .order_by(FaceEmbedding.vector.cosine_distance(embedding))
        .limit(1)
    ).first()

    if result is None:
        return None, None, None, None

    face_embedding, name, face_id, photo_path = result
    stored = np.array(face_embedding.vector, dtype=np.float32)
    cos_sim = np.dot(embedding, stored) / (
        np.linalg.norm(embedding) * np.linalg.norm(stored) + 1e-8
    )
    cos_distance = 1 - cos_sim

    if cos_distance <= settings.UNKNOWN_FACE_THRESHOLD:
        return name, float(cos_distance), face_id, photo_path
    return None, float(cos_distance), None, None