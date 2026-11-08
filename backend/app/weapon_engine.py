"""
Upgraded Weapon Detection Engine (Gun & Knife Specialization with Distance/Multi-Scale Inference).

Features:
- High-Resolution & Multi-Scale Inference: Runs inference at 1024px with multi-scale
  central ROI zoom to capture distant and small weapons (knives, handguns).
- Multi-Scale NMS Fusion: Merges multi-scale detections via Non-Maximum Suppression (NMS),
  preventing duplicate bounding boxes while maximizing recall.
- Distinct Class Labeling: Clearly separates and reports 'Gun' and 'Knife' classes with
  their exact confidence scores.
- Temporal Confirmation & Cooldown: Suppresses single-frame noise and prevents alert spam.
- Clean Frame Guarantee: Never mutates or draws bounding boxes on video frames.
"""
import time
import logging
import cv2
import numpy as np
import torch
import ultralytics.nn.tasks

# Enable PyTorch safe globals for Ultralytics weights
try:
    torch.serialization.add_safe_globals([ultralytics.nn.tasks.DetectionModel])
except Exception:
    pass

from ultralytics import YOLO
from app.config import settings

logger = logging.getLogger(__name__)

import os
from pathlib import Path

def get_allowed_weapon_classes() -> set[str]:
    raw = getattr(settings, "WEAPON_CLASSES", os.getenv("WEAPON_CLASSES", "")).strip()
    return {c.strip().lower() for c in raw.split(",") if c.strip()}

# Specialized weapon keyword mapping to canonical classes
WEAPON_CANONICAL_MAP = {
    "gun": "Gun",
    "pistol": "Gun",
    "handgun": "Gun",
    "rifle": "Gun",
    "firearm": "Gun",
    "revolver": "Gun",
    "shotgun": "Gun",
    "assault rifle": "Gun",
    "knife": "Knife",
    "dagger": "Knife",
    "blade": "Knife",
    "sword": "Knife",
    "machete": "Knife",
    "grenade": "Grenade",
    "bomb": "Explosive",
    "explosive": "Explosive",
    "blunt_weapon": "Blunt Weapon",
    "blunt weapon": "Blunt Weapon",
    "melee_weapon": "Melee Weapon",
    "melee weapon": "Melee Weapon",
}

DEFAULT_WEAPON_KEYWORDS = set(WEAPON_CANONICAL_MAP.keys()).union({
    "weapon", "sniper", "fire_smoke", "fire smoke", "blunt", "melee", "fire"
})

EXCLUDED_CLASSES = {
    "person", "tool", "human", "people", "chair"
}


class WeaponDetectionEngine:
    def __init__(self, model_path: str = None, confidence: float = None):
        self.model_path = model_path or settings.WEAPON_MODEL_PATH
        self.confidence = confidence if confidence is not None else settings.WEAPON_CONFIDENCE
        self.model = None
        self.is_ready = False
        self._load_model()

    def _resolve_model_path(self, path_str: str) -> str:
        """Resolves relative model paths against common base directories."""
        if not path_str:
            return path_str
        p = Path(path_str)
        if p.is_file():
            return str(p)
        # Check relative to backend/
        backend_p = Path(__file__).resolve().parent.parent / path_str
        if backend_p.is_file():
            return str(backend_p)
        # Check relative to project root
        root_p = Path(__file__).resolve().parent.parent.parent / path_str
        if root_p.is_file():
            return str(root_p)
        return path_str

    def _download_hf_weights(self, target_path_str: str):
        """Downloads Subh775/Threat-Detection-YOLOv8n weights from Hugging Face if missing."""
        try:
            root_p = Path(__file__).resolve().parent.parent.parent
            target_path = root_p / (target_path_str or "models/weapon/threat-yolov8n.pt")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            hf_url = "https://huggingface.co/Subh775/Threat-Detection-YOLOv8n/resolve/main/weights/best.pt"
            logger.info(f"[WeaponEngine] Downloading Subh775/Threat-Detection-YOLOv8n from HuggingFace -> {target_path}")
            import urllib.request
            urllib.request.urlretrieve(hf_url, str(target_path))
            logger.info(f"[WeaponEngine] Downloaded model weights successfully.")
        except Exception as exc:
            logger.warning(f"[WeaponEngine] Automatic download from HuggingFace failed: {exc}")

    def _load_model(self):
        try:
            resolved_path = self._resolve_model_path(self.model_path)
            if not resolved_path or not Path(resolved_path).is_file():
                if "threat" in (self.model_path or "").lower() or self.model_path == settings.WEAPON_MODEL_PATH:
                    self._download_hf_weights(self.model_path)
                    resolved_path = self._resolve_model_path(self.model_path)

            if not resolved_path or not Path(resolved_path).is_file():
                raise FileNotFoundError(f"Model file does not exist at '{resolved_path}'")
            logger.info(f"[WeaponEngine] Loading weapon model from: {resolved_path}")
            self.model = YOLO(resolved_path)
            self.is_ready = True
            msg = f"[WeaponEngine] Model successfully loaded ({resolved_path}) with classes: {getattr(self.model, 'names', {})}"
            logger.info(msg)
            print(f"\033[92m{msg}\033[0m")
        except Exception as e:
            self.is_ready = False
            self.model = None
            err_msg = f"[WeaponEngine] FAILED to load weapon model from '{self.model_path}': {e}. Weapon detection disabled."
            logger.error(err_msg, exc_info=True)
            print(f"\033[91m{err_msg}\033[0m")

    def is_weapon_class(self, label: str) -> bool:
        """Determines if a detected class name represents a weapon, ignoring persons and tools."""
        cleaned = (label or "").strip().lower().replace("-", "_")
        if not cleaned or cleaned in EXCLUDED_CLASSES:
            return False
        if cleaned in DEFAULT_WEAPON_KEYWORDS:
            return True
        for kw in DEFAULT_WEAPON_KEYWORDS:
            if kw in cleaned:
                return True
        return False

    def canonical_label(self, raw_label: str) -> str:
        """Maps detected raw class name into a clean canonical label (e.g. 'Gun' or 'Knife')."""
        cleaned = (raw_label or "").strip().lower().replace("-", "_")
        if cleaned in WEAPON_CANONICAL_MAP:
            return WEAPON_CANONICAL_MAP[cleaned]
        for kw, canonical in WEAPON_CANONICAL_MAP.items():
            if kw in cleaned:
                return canonical
        return raw_label.title() if raw_label else "Weapon"

    def _run_single_pass(self, image_np, offset_x=0, offset_y=0, imgsz=1024):
        """Helper to run single scale inference and return candidate detections."""
        raw_candidates = []
        try:
            results = self.model(
                image_np,
                imgsz=imgsz,
                conf=self.confidence,
                verbose=False
            )[0]
            for box in results.boxes:
                conf = float(box.conf[0])
                if conf < self.confidence:
                    continue

                raw_label = self.model.names[int(box.cls[0])]
                if not self.is_weapon_class(raw_label):
                    continue

                bx1, by1, bx2, by2 = map(int, box.xyxy[0])
                x1 = bx1 + offset_x
                y1 = by1 + offset_y
                x2 = bx2 + offset_x
                y2 = by2 + offset_y

                raw_candidates.append({
                    "class_name": self.canonical_label(raw_label),
                    "confidence": round(conf, 3),
                    "bbox": (x1, y1, x2, y2),
                    "w": x2 - x1,
                    "h": y2 - y1,
                })
        except Exception as exc:
            logger.debug(f"[WeaponEngine] Single pass error: {exc}")
        return raw_candidates

    def detect(self, frame) -> list[dict]:
        """
        Runs weapon detection on the provided frame copy using multi-scale inference and NMS fusion.

        Returns structured detections:
            [
                {
                    "class_name": "Gun" | "Knife",
                    "confidence": float,
                    "bbox": (x1, y1, x2, y2)
                },
                ...
            ]
        """
        if not self.is_ready or self.model is None or frame is None:
            return []

        h, w = frame.shape[:2]
        if h == 0 or w == 0:
            return []

        imgsz = settings.WEAPON_INFERENCE_SIZE
        all_candidates = []

        # 1. Full-frame high-resolution pass
        full_pass = self._run_single_pass(frame, offset_x=0, offset_y=0, imgsz=imgsz)
        all_candidates.extend(full_pass)

        # 2. Multi-scale ROI passes — covers both indoor (close) and outdoor (distant/edge)
        # 5 crops: center (distant objects) + 4 corners (wide-angle edge coverage)
        if settings.WEAPON_MULTI_SCALE_ENABLED and w >= 320 and h >= 240:
            crop_w = int(w * 0.55)
            crop_h = int(h * 0.55)
            cx = w - crop_w   # right anchor
            cy = h - crop_h   # bottom anchor
            rois = [
                (0,      0,      crop_w, crop_h),   # top-left
                (cx,     0,      crop_w, crop_h),   # top-right
                (0,      cy,     crop_w, crop_h),   # bottom-left
                (cx,     cy,     crop_w, crop_h),   # bottom-right
                ((w - crop_w) // 2, (h - crop_h) // 2, crop_w, crop_h),  # center (outdoor distant)
            ]
            for ox, oy, cw, ch in rois:
                roi = frame[oy:oy+ch, ox:ox+cw]
                if roi.size > 0:
                    roi_pass = self._run_single_pass(roi, offset_x=ox, offset_y=oy, imgsz=imgsz)
                    all_candidates.extend(roi_pass)

        if not all_candidates:
            return []

        # 3. Non-Maximum Suppression (NMS) to merge multi-scale detections
        boxes_for_nms = []
        confidences_for_nms = []
        for c in all_candidates:
            x1, y1, x2, y2 = c["bbox"]
            boxes_for_nms.append([int(x1), int(y1), max(1, int(x2 - x1)), max(1, int(y2 - y1))])
            confidences_for_nms.append(float(c["confidence"]))

        final_detections = []
        if boxes_for_nms:
            indices = cv2.dnn.NMSBoxes(
                boxes_for_nms,
                confidences_for_nms,
                score_threshold=float(self.confidence),
                nms_threshold=float(settings.WEAPON_NMS_IOU),
            )

            if len(indices) > 0:
                flat_indices = np.asarray(indices).flatten()
                for idx in flat_indices:
                    idx = int(idx)
                    if idx < len(all_candidates):
                        cand = all_candidates[idx]
                        allowed_classes = get_allowed_weapon_classes()
                        if allowed_classes and cand["class_name"].lower() not in allowed_classes:
                            continue
                        final_detections.append({
                            "class_name": cand["class_name"],
                            "confidence": cand["confidence"],
                            "bbox": cand["bbox"],
                        })

        return final_detections


class CameraWeaponTracker:
    """
    Maintains independent temporal confirmation and cooldown state for a single camera.
    """
    def __init__(
        self,
        camera_id: int,
        confirmation_count: int = None,
        window_seconds: float = None,
        cooldown_seconds: float = None,
    ):
        self.camera_id = camera_id
        self.confirmation_count = (
            confirmation_count if confirmation_count is not None else settings.WEAPON_CONFIRMATION_COUNT
        )
        self.window_seconds = (
            window_seconds if window_seconds is not None else settings.WEAPON_CONFIRMATION_WINDOW_SECONDS
        )
        self.cooldown_seconds = (
            cooldown_seconds if cooldown_seconds is not None else settings.WEAPON_COOLDOWN_SECONDS
        )
        self.history: list[tuple[float, str, float, tuple]] = []  # (timestamp, class_name, confidence, bbox)
        self.last_alert_time: float = 0.0

    def register_detection(
        self,
        class_name: str,
        confidence: float,
        bbox: tuple,
        now: float = None,
    ) -> tuple[bool, dict | None]:
        """
        Registers a valid in-zone weapon detection.

        Returns (is_confirmed, event_payload_or_None).
        `is_confirmed` is True ONLY if:
        1. At least `confirmation_count` detections occur within `window_seconds`.
        2. Time since `last_alert_time` >= `cooldown_seconds`.
        """
        curr_time = now if now is not None else time.time()

        # Prune history outside the sliding time window
        window_start = curr_time - self.window_seconds
        self.history = [h for h in self.history if h[0] >= window_start]

        # Record this detection
        self.history.append((curr_time, class_name, confidence, bbox))
        logger.info(
            f"[WeaponTracker:cam{self.camera_id}] Hit: {class_name} ({confidence:.2f}) "
            f"-> {len(self.history)}/{self.confirmation_count} in window"
        )

        # Check temporal confirmation count
        if len(self.history) >= self.confirmation_count:
            # Check cooldown period
            elapsed = curr_time - self.last_alert_time
            if elapsed < self.cooldown_seconds:
                logger.info(
                    f"[WeaponTracker:cam{self.camera_id}] Weapon confirmed but cooldown active "
                    f"({self.cooldown_seconds - elapsed:.1f}s remaining)"
                )
                return False, None

            self.last_alert_time = curr_time
            # Pick the detection with the highest confidence in this window
            best = max(self.history, key=lambda item: item[2])
            payload = {
                "class_name": best[1],
                "confidence": best[2],
                "bbox": best[3],
                "confirmation_count": len(self.history),
                "camera_id": self.camera_id,
                "timestamp": curr_time,
            }
            logger.warning(
                f"[WeaponTracker:cam{self.camera_id}] 🚨 WEAPON CONFIRMED: {best[1]} (conf={best[2]:.2f}) -> FIRING ALERT"
            )
            self.history.clear()
            return True, payload

        return False, None

    def reset(self):
        """Clears detection history for this camera."""
        self.history.clear()


# Global weapon engine singleton
weapon_engine = WeaponDetectionEngine()
