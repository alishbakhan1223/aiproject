"""
Lightweight per-camera person tracking (recognition-throttling).

Wraps supervision's built-in ByteTrack, which consumes the person boxes
already produced by the existing YOLOv8n pass in object_engine.py — it
runs no detection model of its own, so this adds essentially no extra
inference cost. Its only job is to assign a stable track_id to the same
physical person across consecutive detection cycles, so the far more
expensive InsightFace step doesn't have to re-run on every single cycle
for someone who is just standing there.

We use supervision's built-in sv.ByteTrack rather than the standalone
`trackers` package: `trackers` requires numpy>=2.0.2, which conflicts
with numpy==1.26.4 (needed by torch/insightface/onnxruntime in this
project). sv.ByteTrack has no such constraint.

One PersonTracker instance must be created per camera — ByteTrack keeps
internal state (active tracks, Kalman filters) per instance, so cameras
must never share one.

FILE PATH: backend/app/person_tracker.py
ACTION: CREATE NEW FILE
"""
import numpy as np
import supervision as sv


class PersonTracker:
    def __init__(self, lost_track_buffer: int = 60):
        self._tracker = sv.ByteTrack(lost_track_buffer=lost_track_buffer)

    def update(self, person_detections: list[dict]) -> list[dict]:
        """
        person_detections: output of object_engine.detect_objects(), already
        filtered down to label == "person".

        Returns: [{"track_id": int, "box": (x1, y1, x2, y2)}, ...]
        """
        if not person_detections:
            self._tracker.update_with_detections(sv.Detections.empty())
            return []

        xyxy = np.array([d["box"] for d in person_detections], dtype=np.float32)
        confidence = np.array([d["confidence"] for d in person_detections], dtype=np.float32)
        class_id = np.zeros(len(person_detections), dtype=int)

        detections = sv.Detections(xyxy=xyxy, confidence=confidence, class_id=class_id)
        tracked = self._tracker.update_with_detections(detections)

        results = []
        for box, track_id in zip(tracked.xyxy, tracked.tracker_id):
            if track_id is None:
                continue
            x1, y1, x2, y2 = map(int, box)
            results.append({"track_id": int(track_id), "box": (x1, y1, x2, y2)})
        return results


def match_face_to_track(face_box, tracked_persons: list[dict]):
    """
    Finds which tracked person a detected face belongs to, by checking
    whether the face box's center point falls inside a tracked person's
    body box. Returns None (fail open — always due for recognition) if the
    face isn't inside any currently tracked person box.
    """
    fx1, fy1, fx2, fy2 = face_box
    face_cx, face_cy = (fx1 + fx2) / 2, (fy1 + fy2) / 2

    for t in tracked_persons:
        x1, y1, x2, y2 = t["box"]
        if x1 <= face_cx <= x2 and y1 <= face_cy <= y2:
            return t["track_id"]
    return None