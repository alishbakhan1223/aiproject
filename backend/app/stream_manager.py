"""
Thread-safe in-memory store of the latest JPEG frame per camera, so the
FastAPI MJPEG endpoint can serve a live view without touching the camera
directly (the camera_worker thread owns the capture device).

Uses threading.Event per camera so the MJPEG endpoint can block until a
new frame arrives instead of polling with sleep().
"""
import threading

_lock = threading.Lock()
_latest_frames: dict[int, bytes] = {}
_frame_events: dict[int, threading.Event] = {}


def _get_event(camera_id: int) -> threading.Event:
    """Get or create a per-camera Event for push-based frame notification."""
    if camera_id not in _frame_events:
        _frame_events[camera_id] = threading.Event()
    return _frame_events[camera_id]


def publish_frame(camera_id: int, jpeg_bytes: bytes):
    with _lock:
        _latest_frames[camera_id] = jpeg_bytes
        evt = _get_event(camera_id)
    evt.set()  # Wake up any waiting MJPEG generator immediately


def get_latest_frame(camera_id: int) -> bytes | None:
    with _lock:
        return _latest_frames.get(camera_id)


def wait_for_frame(camera_id: int, timeout: float = 0.5) -> bytes | None:
    """Block until a new frame is published, then return it. Returns None on timeout."""
    with _lock:
        evt = _get_event(camera_id)
    evt.wait(timeout=timeout)
    evt.clear()
    with _lock:
        return _latest_frames.get(camera_id)


def clear_frame(camera_id: int):
    with _lock:
        _latest_frames.pop(camera_id, None)
        _frame_events.pop(camera_id, None)
