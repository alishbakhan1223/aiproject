"""
Object detection using YOLOv8 (Ultralytics), free & open-source.

Two-tier detection:
  - LIGHT model (yolov8n) runs on every inference frame for speed.
  - FORENSIC model (yolov8m) is only invoked to re-confirm a frame right after
    a trespass-worthy event (unknown person / restricted object in a zone),
    trading a bit of extra latency for higher accuracy exactly when it matters.
"""
import torch
import ultralytics.nn.tasks

try:
    if hasattr(torch.serialization, "add_safe_globals"):
        torch.serialization.add_safe_globals([ultralytics.nn.tasks.DetectionModel])
except Exception:
    pass
from ultralytics import YOLO
from app.config import settings

_light_model = YOLO(settings.LIGHT_MODEL)
_forensic_model = None  # lazy-loaded so idle systems don't pay the extra RAM cost


def _get_forensic_model():
    global _forensic_model
    if _forensic_model is None:
        _forensic_model = YOLO(settings.FORENSIC_MODEL)
    return _forensic_model


def _run(model, frame):
    results = model(frame, conf=0.35, classes=[0], verbose=False)[0]
    detections = []
    for box in results.boxes:
        conf = float(box.conf[0])
        if conf < settings.CONFIDENCE_THRESHOLD:
            continue
        label = model.names[int(box.cls[0])].lower()
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        detections.append(
            {"label": label, "confidence": conf, "box": (x1, y1, x2, y2)}
        )
    return detections


def detect_objects(frame):
    """Fast pass using the light model. Used continuously on every camera."""
    return _run(_light_model, frame)


def detect_objects_forensic(frame):
    """Slower, more accurate pass. Only called right after a trespass event."""
    return _run(_get_forensic_model(), frame)


def filter_restricted(detections):
    return [d for d in detections if d["label"] in settings.RESTRICTED_OBJECTS]


def box_center(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2, (y1 + y2) / 2)
