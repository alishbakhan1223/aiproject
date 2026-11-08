"""
Face quality assessment, blur filtering, and orientation gating.

Computes a comprehensive face quality score based on:
1. Sharpness / blur (Laplacian variance of the cropped face)
2. Resolution / pixel size (minimum bounding box dimension)
3. Detection confidence (InsightFace det_score)
4. Head pose (yaw, pitch, roll alignment)
5. Lighting / exposure (brightness distribution)

Faces failing the quality threshold are rejected immediately before saving
to disk or database, preventing storage bloat and poor embeddings.

All thresholds are read from app.config.settings, so tuning FACE_MIN_SIZE_PX /
FACE_MIN_SHARPNESS / FACE_MIN_QUALITY_SCORE / FACE_MAX_YAW_DEG etc. in
config.py (or .env) takes effect here automatically — no changes needed in
this file for the close-range vs 10-12 feet distance tuning.
"""
import cv2
import numpy as np
import logging

from app.config import settings

logger = logging.getLogger(__name__)


def _variance_of_laplacian(gray_image: np.ndarray) -> float:
    """Standard blur metric: low variance of the Laplacian = flat/blurry image."""
    if gray_image is None or gray_image.size == 0:
        return 0.0
    return float(cv2.Laplacian(gray_image, cv2.CV_64F).var())


def evaluate_face_quality(frame: np.ndarray, face) -> dict:
    """
    Evaluates comprehensive quality score for a detected face.
    Returns:
        {
            "quality_score": float,  # composite 0.0 - 100.0+
            "is_acceptable": bool,   # passed all quality & frontality gates
            "sharpness": float,      # raw Laplacian variance
            "det_score": float,      # detector confidence
            "brightness": float,     # mean pixel intensity (0-255)
            "size_px": tuple[int, int],  # (width, height)
            "rejection_reason": str | None
        }
    """
    if frame is None or face is None:
        return {
            "quality_score": 0.0,
            "is_acceptable": False,
            "sharpness": 0.0,
            "det_score": 0.0,
            "brightness": 0.0,
            "size_px": (0, 0),
            "rejection_reason": "Missing frame or face",
        }

    h_img, w_img = frame.shape[:2]
    x1, y1, x2, y2 = map(int, face.bbox)
    x1, y1 = max(x1, 0), max(y1, 0)
    x2, y2 = min(x2, w_img), min(y2, h_img)
    w, h = x2 - x1, y2 - y1

    if w < settings.FACE_MIN_SIZE_PX or h < settings.FACE_MIN_SIZE_PX:
        return {
            "quality_score": 0.0,
            "is_acceptable": False,
            "sharpness": 0.0,
            "det_score": float(getattr(face, "det_score", 0.0)),
            "brightness": 0.0,
            "size_px": (w, h),
            "rejection_reason": f"Face too small ({w}x{h} < {settings.FACE_MIN_SIZE_PX}px)",
        }

    det_score = float(getattr(face, "det_score", 1.0))
    if det_score < settings.FACE_MIN_DET_SCORE:
        return {
            "quality_score": 0.0,
            "is_acceptable": False,
            "sharpness": 0.0,
            "det_score": det_score,
            "brightness": 0.0,
            "size_px": (w, h),
            "rejection_reason": f"Low detection score ({det_score:.2f} < {settings.FACE_MIN_DET_SCORE:.2f})",
        }

    # Head pose check
    pose = getattr(face, "pose", None)
    pose_penalty = 0.0
    if pose is not None:
        yaw, pitch, roll = [float(v) for v in pose]
        if (
            abs(yaw) > settings.FACE_MAX_YAW_DEG
            or abs(pitch) > settings.FACE_MAX_PITCH_DEG
            or abs(roll) > settings.FACE_MAX_ROLL_DEG
        ):
            return {
                "quality_score": 0.0,
                "is_acceptable": False,
                "sharpness": 0.0,
                "det_score": det_score,
                "brightness": 0.0,
                "size_px": (w, h),
                "rejection_reason": f"Non-frontal pose (yaw={yaw:.1f}, pitch={pitch:.1f}, roll={roll:.1f})",
            }
        pose_penalty = (abs(yaw) + abs(pitch) + abs(roll)) * 0.3

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return {
            "quality_score": 0.0,
            "is_acceptable": False,
            "sharpness": 0.0,
            "det_score": det_score,
            "brightness": 0.0,
            "size_px": (w, h),
            "rejection_reason": "Empty crop",
        }

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    sharpness = _variance_of_laplacian(gray)

    # Lighting / exposure score
    mean_brightness = float(np.mean(gray))
    if mean_brightness < 30.0:
        brightness_factor = 0.4  # too dark
    elif mean_brightness > 230.0:
        brightness_factor = 0.5  # overexposed
    elif 60.0 <= mean_brightness <= 190.0:
        brightness_factor = 1.0  # optimal lighting
    else:
        brightness_factor = 0.8

    # Check minimum blur threshold
    if sharpness < settings.FACE_MIN_SHARPNESS:
        return {
            "quality_score": round(sharpness, 2),
            "is_acceptable": False,
            "sharpness": round(sharpness, 2),
            "det_score": det_score,
            "brightness": round(mean_brightness, 1),
            "size_px": (w, h),
            "rejection_reason": f"Blurry face (sharpness {sharpness:.1f} < {settings.FACE_MIN_SHARPNESS:.1f})",
        }

    # Combined quality metric:
    # Sharpness (normalized base) + Detection Confidence (up to 30) + Brightness (up to 20) - Pose penalty
    # Scale sharpness so a clear face (sharpness ~100-300) produces a score 60-100+
    sharpness_contrib = min(70.0, (sharpness / 150.0) * 50.0)
    det_contrib = det_score * 30.0
    brightness_contrib = brightness_factor * 20.0
    composite_score = round(max(0.0, sharpness_contrib + det_contrib + brightness_contrib - pose_penalty), 2)

    is_acceptable = composite_score >= settings.FACE_MIN_QUALITY_SCORE

    return {
        "quality_score": composite_score,
        "is_acceptable": is_acceptable,
        "sharpness": round(sharpness, 2),
        "det_score": det_score,
        "brightness": round(mean_brightness, 1),
        "size_px": (w, h),
        "rejection_reason": None if is_acceptable else f"Composite quality too low ({composite_score} < {settings.FACE_MIN_QUALITY_SCORE})",
    }


def is_face_clear(frame: np.ndarray, face) -> bool:
    """Backward-compatible helper."""
    res = evaluate_face_quality(frame, face)
    return res["is_acceptable"]


def is_front_facing(face) -> bool:
    """Backward-compatible helper."""
    pose = getattr(face, "pose", None)
    if pose is None:
        return True
    yaw, pitch, roll = [float(v) for v in pose]
    return (
        abs(yaw) <= settings.FACE_MAX_YAW_DEG
        and abs(pitch) <= settings.FACE_MAX_PITCH_DEG
        and abs(roll) <= settings.FACE_MAX_ROLL_DEG
    )