"""
One CameraWorker runs per camera in its own thread, so multiple cameras
process independently.

Pipeline per frame:
  capture -> publish live frame (every frame, for the MJPEG stream)
          -> every Nth frame: YOLOv8n objects + InsightFace faces + Weapon detection
          -> zone check (only alert if inside the camera's defined zone, if any)
          -> log event -> push to Redis Stream -> WhatsApp alert
          -> if trespass-worthy (unknown person / restricted object / weapon):
             re-run detection with the heavier YOLOv8m "forensic" model and
             log a confirmation event with higher confidence.
"""
import cv2
import json
import time
import threading
import logging
import os
from datetime import datetime

class VideoStreamGrabber:
    def __init__(self, src=0):
        self.src = src
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ret = False
        self.frame = None
        self._lock = threading.Lock()
        if self.cap.isOpened():
            self.ret, self.frame = self.cap.read()
        self.stopped = False
        self.thread = threading.Thread(target=self.update, args=(), daemon=True)
        self.thread.start()

    def update(self):
        while not self.stopped:
            if not self.cap or not self.cap.isOpened():
                break
            ret, frame = self.cap.read()
            if not ret or frame is None or getattr(frame, "size", 0) == 0:
                time.sleep(0.01)
                continue
            with self._lock:
                self.ret, self.frame = ret, frame

    def read(self):
        with self._lock:
            return self.ret, self.frame

    def release(self):
        self.stopped = True
        if hasattr(self, "thread") and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        try:
            if self.cap and self.cap.isOpened():
                self.cap.release()
        except Exception:
            pass

# Force TCP for stability, sufficient probe/analyzeduration for stream header indexing, and nobuffer
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|analyzeduration;500000|probesize;1048576|max_delay;500000"

from app.database import SessionLocal
from app.models import Event, Zone
from app.face_engine import extract_faces, match_face, is_frontal_face
from app.face_quality import evaluate_face_quality
from app.object_engine import (
    detect_objects, detect_objects_forensic, filter_restricted, box_center,
)
from app.redis_stream import push_event
from app.whatsapp import (
    send_whatsapp_text,
    send_whatsapp_image_alert,
    build_unknown_person_message,
    build_restricted_object_message,
    build_weapon_message,
)
from app.alert_dispatcher import dispatch_image_alert
from app.unknown_person_service import resolve_unknown_person
from app.spec_unknowns_service import register_spec_unknown
from app.weapon_engine import weapon_engine, CameraWeaponTracker
from app.config import settings
from app.stream_manager import publish_frame, clear_frame

logger = logging.getLogger(__name__)
INFER_EVERY_N_FRAMES = 15  # Run detection every 15 frames (~2 FPS at 30 FPS input)
STREAM_JPEG_QUALITY = 70


def _point_in_zone(point, polygon_points) -> bool:
    import numpy as np
    poly = np.array(polygon_points, dtype=np.int32)
    return cv2.pointPolygonTest(poly, point, False) >= 0


class CameraWorker:
    def __init__(self, camera_id: int, camera_name: str, source: str):
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.source = int(source) if str(source).isdigit() else source
        self._running = False
        self._thread = None
        self._detection_thread = None
        self.zone_polygon = self._load_zone()
        self._detection_frame = None
        self._detection_frame_time = None
        self._detection_lock = threading.Lock()
        self._detection_event = threading.Event()
        self.weapon_tracker = CameraWeaponTracker(self.camera_id)
        # Same banday ke baar baar alerts rokne ke liye cooldown
        self._last_alert = {}
        self.ALERT_COOLDOWN_SEC = 30

        self.status = {
            "camera_id": camera_id,
            "camera_name": camera_name,
            "running": False,
            "state": "initializing",
            "last_frame_at": None,
            "frames_processed": 0,
            "reconnect_count": 0,
            "fps_source": None,
            "capture_fps": None,
            "frame_age_ms": None,
            "dropped_frames": 0,
            "frames_delivered": 0,
            "stream_errors": 0,
            "jpeg_encode_ms": None,
            "yolo_fps": None,
            "yolo_inference_ms": None,
            "insightface_inference_ms": None,
            "detection_frame_age_ms": None,
            "detection_frames_skipped": 0,
            "latest_detection_at": None,
        }

    def _load_zone(self):
        db = SessionLocal()
        try:
            zone = db.query(Zone).filter(Zone.camera_id == self.camera_id).first()
            return json.loads(zone.polygon) if zone else None
        finally:
            db.close()

    def start(self):
        if self._running:
            return
        self._running = True
        self.status["running"] = True
        self._thread = threading.Thread(target=self._run_capture, daemon=True, name=f"camera-capture-{self.camera_id}")
        self._detection_thread = threading.Thread(target=self._run_detection, daemon=True, name=f"camera-detect-{self.camera_id}")
        self._thread.start()
        self._detection_thread.start()
        _active_workers[self.camera_id] = self

    def stop(self):
        self._running = False
        self.status["running"] = False
        self.status["state"] = "stopped"
        if self._detection_thread and self._detection_thread.is_alive():
            self._detection_event.set()
            self._detection_thread.join(timeout=2.0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.5)
        clear_frame(self.camera_id)

    def _save_snapshot(self, frame, category: str = "misc") -> str:
        folder = f"{settings.SNAPSHOT_DIR}/{category}"
        os.makedirs(folder, exist_ok=True)
        filename = f"{self.camera_name}_{int(time.time()*1000)}.jpg"
        path = f"{folder}/{filename}"
        cv2.imwrite(path, frame)
        return path

    def _log_and_alert(self, event_type, person_name=None, is_unknown=False,
                         object_name=None, confidence=None, frame=None, in_zone=None,
                         snapshot_path=None, category: str = "misc"):
        if snapshot_path is None and frame is not None:
            snapshot_path = self._save_snapshot(frame, category=category)
        db = SessionLocal()
        try:
            event = Event(
                event_type=event_type,
                camera_name=self.camera_name,
                timestamp=datetime.utcnow(),
                snapshot_path=snapshot_path,
                person_name=person_name,
                is_unknown=is_unknown,
                object_name=object_name,
                confidence=confidence,
                in_zone=in_zone,
            )
            db.add(event)
            db.commit()
        finally:
            db.close()

        push_event({
            "event_type": event_type,
            "camera_name": self.camera_name,
            "timestamp": str(datetime.utcnow()),
            "person_name": person_name,
            "object_name": object_name,
            "confidence": confidence,
        })

        if event_type == "unknown_person":
            msg = build_unknown_person_message(
                self.camera_name, datetime.utcnow().strftime("%I:%M %p"), confidence or 0
            )
            if person_name:
                msg = f"{msg}\nIdentity: {person_name}"
            dispatch_image_alert(snapshot_path, msg)
        elif event_type == "restricted_object":
            msg = build_restricted_object_message(
                self.camera_name, object_name, datetime.utcnow().strftime("%I:%M %p"), confidence or 0
            )
            dispatch_image_alert(snapshot_path, msg)
        elif event_type == "weapon_detected":
            msg = build_weapon_message(
                self.camera_name,
                object_name or "Weapon",
                datetime.utcnow().strftime("%I:%M %p"),
                confidence or 0,
                zone_name=f"Camera {self.camera_id} Zone" if in_zone else None,
                forensic_confirmed=True,
            )
            dispatch_image_alert(snapshot_path, msg)

    def _forensic_confirm(self, frame, trigger_label):
        detections = detect_objects_forensic(frame)
        best = max(detections, key=lambda d: d["confidence"], default=None)
        self._log_and_alert(
            "forensic_confirmation",
            object_name=best["label"] if best else trigger_label,
            confidence=best["confidence"] if best else None,
            frame=frame,
            category="forensic",
        )

    def _in_zone_or_no_zone(self, box) -> bool:
        if not self.zone_polygon:
            return True
        return _point_in_zone(box_center(box), self.zone_polygon)

    def _zone_status(self, box):
        """None = zone off (koi zone bana hi nahi), True = inside, False = outside."""
        if not self.zone_polygon:
            return None
        return _point_in_zone(box_center(box), self.zone_polygon)

    def _cooldown_ok(self, key) -> bool:
        now = time.time()
        if now - self._last_alert.get(key, 0) < self.ALERT_COOLDOWN_SEC:
            return False
        self._last_alert[key] = now
        return True

    def _run_capture(self):
        logger.info(f"[{self.camera_name}] Starting frame capture thread. Source: {self.source}")
        latest_frame = [None]
        latest_frame_time = [None]
        frame_lock = threading.Lock()
        reader_stop = threading.Event()

        def reader(cap):
            frames_read = 0
            start_time = time.time()
            while self._running and not reader_stop.is_set():
                if not cap or not cap.isOpened():
                    break
                ret, frame = cap.read()
                if not ret or frame is None or getattr(frame, "size", 0) == 0:
                    time.sleep(0.01)
                    if not self._running or reader_stop.is_set():
                        break
                    continue

                # Check valid 3-channel frame shape
                if len(frame.shape) != 3 or frame.shape[0] == 0 or frame.shape[1] == 0:
                    continue

                capture_time = time.time()
                with frame_lock:
                    if latest_frame[0] is not None:
                        self.status["dropped_frames"] += 1
                    latest_frame[0] = frame
                    latest_frame_time[0] = capture_time
                frames_read += 1

                elapsed = time.time() - start_time
                if elapsed >= 1.0:
                    self.status["capture_fps"] = round(frames_read / elapsed, 1)
                    frames_read = 0
                    start_time = time.time()

        while self._running:
            self.status["state"] = "connecting"
            cap = None
            try:
                if isinstance(self.source, str) and (self.source.startswith("http") or self.source.startswith("rtsp")):
                    cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
                elif isinstance(self.source, int) or (isinstance(self.source, str) and self.source.isdigit()):
                    cap = cv2.VideoCapture(int(self.source), cv2.CAP_DSHOW)
                else:
                    cap = cv2.VideoCapture(self.source)

                if cap:
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception as e:
                logger.error(f"[{self.camera_name}] Error initializing VideoCapture: {e}")
                cap = None

            if not cap or not cap.isOpened():
                logger.error(f"[{self.camera_name}] FAILED to open camera source: {self.source}")
                self.status["state"] = "failed"
                time.sleep(5.0)
                self.status["reconnect_count"] += 1
                continue

            self.status["state"] = "connected"
            source_fps = cap.get(cv2.CAP_PROP_FPS)
            self.status["fps_source"] = round(source_fps, 1) if (source_fps and source_fps > 0) else None

            reader_stop.clear()
            reader_thread = threading.Thread(target=reader, args=(cap,), daemon=True)
            reader_thread.start()

            try:
                while self._running and reader_thread.is_alive():
                    with frame_lock:
                        frame = latest_frame[0]
                        frame_time = latest_frame_time[0]
                        latest_frame[0] = None
                        latest_frame_time[0] = None

                    if frame is None:
                        time.sleep(0.01)
                        continue

                    self.status["frames_processed"] += 1

                    if frame_time:
                        self.status["frame_age_ms"] = round((time.time() - frame_time) * 1000, 1)

                    try:
                        t_enc = time.time()
                        ok_jpeg, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, STREAM_JPEG_QUALITY])
                        self.status["jpeg_encode_ms"] = round((time.time() - t_enc) * 1000, 1)
                        if ok_jpeg and buf is not None:
                            publish_frame(self.camera_id, buf.tobytes())
                            self.status["frames_delivered"] += 1
                        else:
                            self.status["stream_errors"] += 1
                    except Exception:
                        self.status["stream_errors"] += 1

                    self.status["last_frame_at"] = datetime.utcnow().isoformat()

                    if self.status["frames_processed"] % INFER_EVERY_N_FRAMES == 0:
                        with self._detection_lock:
                            if self._detection_frame is not None:
                                self.status["detection_frames_skipped"] += 1
                            self._detection_frame = frame.copy()
                            self._detection_frame_time = frame_time
                        self._detection_event.set()

            except Exception as e:
                logger.error(f"[{self.camera_name}] Capture thread error: {e}", exc_info=True)
            finally:
                reader_stop.set()
                if reader_thread and reader_thread.is_alive():
                    reader_thread.join(timeout=1.5)
                try:
                    if cap and cap.isOpened():
                        cap.release()
                except Exception:
                    pass

                if self._running:
                    logger.warning(f"[{self.camera_name}] Stream disconnected. Reconnecting in 5s...")
                    self.status["state"] = "reconnecting"
                    self.status["reconnect_count"] += 1
                    time.sleep(5.0)

    def _run_detection(self):
        logger.info(f"[{self.camera_name}] Starting detection thread")
        db = SessionLocal()
        yolo_count = 0
        yolo_fps_start = time.time()

        try:
            while self._running:
                self._detection_event.wait(timeout=0.5)
                self._detection_event.clear()

                with self._detection_lock:
                    frame = self._detection_frame
                    frame_capture_time = self._detection_frame_time
                    self._detection_frame = None
                    self._detection_frame_time = None

                if frame is None:
                    continue

                if frame_capture_time:
                    self.status["detection_frame_age_ms"] = round(
                        (time.time() - frame_capture_time) * 1000, 1
                    )

                try:
                    # 1. --- Object Detection (Person & Restricted Items) ---
                    t_yolo = time.time()
                    detections = detect_objects(frame)
                    self.status["yolo_inference_ms"] = round((time.time() - t_yolo) * 1000, 1)

                    for obj in filter_restricted(detections):
                        inside = self._in_zone_or_no_zone(obj["box"])
                        if not inside:
                            continue
                        self._log_and_alert(
                            "restricted_object", object_name=obj["label"],
                            confidence=obj["confidence"], frame=frame,
                            in_zone=self._zone_status(obj["box"]),
                            category="restricted",
                        )
                        self._forensic_confirm(frame, obj["label"])

                    # 2. --- Weapon Detection Integration ---
                    weapon_detections = weapon_engine.detect(frame)
                    if weapon_detections:
                        logger.info(
                            f"[{self.camera_name}] [WeaponEngine] Candidates: "
                            f"{[(w.get('class_name'), round(w.get('confidence', 0), 2)) for w in weapon_detections]}"
                        )
                    for w_obj in weapon_detections:
                        w_box = w_obj.get("box") or w_obj.get("bbox")
                        if not w_box:
                            continue
                        inside = self._in_zone_or_no_zone(w_box)
                        if not inside:
                            continue

                        is_confirmed, payload = self.weapon_tracker.register_detection(
                            class_name=w_obj.get("label") or w_obj.get("class_name", "Weapon"),
                            confidence=w_obj.get("confidence", 0.0),
                            bbox=w_box
                        )
                        if is_confirmed and payload:
                            self._log_and_alert(
                                "weapon_detected",
                                object_name=payload["class_name"],
                                confidence=payload["confidence"],
                                frame=frame,
                                in_zone=self._zone_status(w_box),
                                category="weapon",
                            )
                            self._forensic_confirm(frame, payload["class_name"])

                    # 3. --- Face Recognition with Quality Gating ---
                    try:
                        t_face = time.time()
                        faces = extract_faces(frame)
                        self.status["insightface_inference_ms"] = round((time.time() - t_face) * 1000, 1)

                        seen_unknown_ids_in_frame = set()
                        for face in faces:
                            # Gated by extract_faces
                            box = tuple(map(int, face.bbox))
                            zone_state = self._zone_status(box)   # True / False / None (zone off)
                            det_conf = float(getattr(face, "det_score", 0.0))

                            # Match against registered known faces
                            name, distance, face_id, photo_path = match_face(face.embedding, db)
                            if name:
                                # KNOWN: poora frame dikhao
                                if self._cooldown_ok(f"known:{name}"):
                                    self._log_and_alert(
                                        "known_person", person_name=name,
                                        confidence=1 - (distance or 0), in_zone=zone_state,
                                        frame=frame, category="known",
                                    )
                            else:
                                # Zone bana hua hai aur banda bahar hai -> unknown alert nahi
                                if zone_state is False:
                                    continue
                                quality_res = getattr(face, "quality_info", None) or evaluate_face_quality(frame, face)
                                quality_score = quality_res.get("quality_score", 0.0)

                                # UNKNOWN: sirf face crop + unique ID
                                unknown_person, is_new = resolve_unknown_person(
                                    face.embedding, frame, db, self.camera_name,
                                    quality_score=quality_score,
                                    exclude_person_ids=seen_unknown_ids_in_frame,
                                    bbox=face.bbox,
                                )
                                seen_unknown_ids_in_frame.add(unknown_person.id)
                                register_spec_unknown(unknown_person.id, self.camera_id)
                                label = f"Unknown-{unknown_person.id:03d}"
                                if is_new or self._cooldown_ok(f"unk:{unknown_person.id}"):
                                    self._log_and_alert(
                                        "unknown_person", person_name=label, is_unknown=True,
                                        confidence=det_conf, in_zone=zone_state,
                                        snapshot_path=unknown_person.representative_snapshot_path,
                                    )
                                if is_new:
                                    self._forensic_confirm(frame, label)
                    except Exception as face_exc:
                        # A single bad DB transaction (or any other error) inside face
                        # recognition must NEVER be allowed to poison this long-lived
                        # `db` session for the rest of this camera's lifetime — without
                        # this rollback, every future frame's known/unknown lookup would
                        # silently keep failing until the backend is restarted.
                        logger.error(f"[{self.camera_name}] Face recognition error: {face_exc}", exc_info=True)
                        try:
                            db.rollback()
                        except Exception:
                            pass

                    self.status["latest_detection_at"] = datetime.utcnow().isoformat()

                except Exception as e:
                    logger.error(f"[{self.camera_name}] Error during detection: {e}", exc_info=True)
                    try:
                        db.rollback()
                    except Exception:
                        pass

                yolo_count += 1
                elapsed = time.time() - yolo_fps_start
                if elapsed >= 5.0:
                    self.status["yolo_fps"] = round(yolo_count / elapsed, 2)
                    yolo_count = 0
                    yolo_fps_start = time.time()

        except Exception as e:
            logger.error(f"[{self.camera_name}] Unexpected error in detection thread: {e}", exc_info=True)
        finally:
            db.close()
            logger.info(f"[{self.camera_name}] Detection thread stopped.")

    def _run(self):
        self._run_capture()

_active_workers: dict[int, CameraWorker] = {}

def start_camera(camera_id: int, camera_name: str, source: str):
    if camera_id in _active_workers and _active_workers[camera_id].status["running"]:
        return
    worker = CameraWorker(camera_id, camera_name, source)
    worker.start()

def stop_camera(camera_id: int):
    worker = _active_workers.pop(camera_id, None)
    if worker:
        worker.stop()

def get_all_worker_status():
    return [w.status for w in _active_workers.values()]

def refresh_zone(camera_id: int):
    worker = _active_workers.get(camera_id)
    if worker:
        worker.zone_polygon = worker._load_zone()