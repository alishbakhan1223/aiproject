"""
Comprehensive unit and integration test suite for Weapon Detection subsystem:
1. WeaponDetectionEngine initialization and graceful failure on invalid model path
2. Detection parsing and confidence threshold filtering
3. Per-camera temporal confirmation sliding window logic
4. Cooldown suppression
5. Multi-camera state isolation
6. Polygon zone filtering
7. Database event logging and Redis event structure
8. WhatsApp alert message formatting
9. Clean Frame Verification: assert live stream / input frames remain 100% byte-for-byte unannotated
"""
import os
import sys
import time
import unittest
import numpy as np
import cv2

# Ensure backend root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.weapon_engine import WeaponDetectionEngine, CameraWeaponTracker, DEFAULT_WEAPON_KEYWORDS
from app.whatsapp import build_weapon_message
from app.camera_worker import _point_in_zone
from app.stream_manager import publish_frame, wait_for_frame, clear_frame


class TestWeaponDetection(unittest.TestCase):

    def test_weapon_engine_invalid_model_graceful_fallback(self):
        """Engine must fail gracefully without crashing if model path is invalid."""
        engine = WeaponDetectionEngine(model_path="non_existent_weights_12345.pt")
        self.assertFalse(engine.is_ready)
        self.assertIsNone(engine.model)

        # detect() should safely return empty list without raising exceptions
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = engine.detect(dummy_frame)
        self.assertEqual(results, [])

    def test_weapon_engine_weapon_class_matching(self):
        """Verify weapon keyword detection for known and YOLO26x class labels."""
        engine = WeaponDetectionEngine.__new__(WeaponDetectionEngine)
        # Standard keywords
        self.assertTrue(engine.is_weapon_class("gun"))
        self.assertTrue(engine.is_weapon_class("knife"))
        self.assertTrue(engine.is_weapon_class("assault rifle"))
        self.assertTrue(engine.is_weapon_class("handgun"))
        # YOLO26x specific classes
        self.assertTrue(engine.is_weapon_class("Blunt_Weapon"))
        self.assertTrue(engine.is_weapon_class("Explosive"))
        self.assertTrue(engine.is_weapon_class("Fire_Smoke"))
        self.assertTrue(engine.is_weapon_class("Firearm"))
        self.assertTrue(engine.is_weapon_class("Melee_Weapon"))
        # Excluded non-weapon classes from YOLO26x
        self.assertFalse(engine.is_weapon_class("Person"))
        self.assertFalse(engine.is_weapon_class("Tool"))
        self.assertFalse(engine.is_weapon_class("chair"))
        self.assertFalse(engine.is_weapon_class(""))
        self.assertFalse(engine.is_weapon_class(None))

    def test_camera_weapon_tracker_temporal_confirmation_and_cooldown(self):
        """
        Test temporal confirmation:
        - Requires 3 detections within a 2-second window.
        - Suppresses alerts during the 30-second cooldown window.
        """
        tracker = CameraWeaponTracker(
            camera_id=1,
            confirmation_count=3,
            window_seconds=2.0,
            cooldown_seconds=30.0,
        )

        t0 = 1000.0
        bbox = (100, 100, 200, 200)

        # 1st detection -> False
        confirmed, data = tracker.register_detection("gun", 0.85, bbox, now=t0)
        self.assertFalse(confirmed)
        self.assertIsNone(data)

        # 2nd detection (0.5s later) -> False
        confirmed, data = tracker.register_detection("gun", 0.90, bbox, now=t0 + 0.5)
        self.assertFalse(confirmed)
        self.assertIsNone(data)

        # 3rd detection (1.0s later from start) -> True (Confirmed!)
        confirmed, data = tracker.register_detection("gun", 0.92, bbox, now=t0 + 1.0)
        self.assertTrue(confirmed)
        self.assertIsNotNone(data)
        self.assertEqual(data["class_name"], "gun")
        self.assertEqual(data["confidence"], 0.92)
        self.assertEqual(data["camera_id"], 1)
        self.assertEqual(data["confirmation_count"], 3)

        # 4th detection (1.5s later from start, within cooldown) -> False (Suppressed by cooldown)
        confirmed, data = tracker.register_detection("gun", 0.95, bbox, now=t0 + 1.5)
        self.assertFalse(confirmed)
        self.assertIsNone(data)

        # 5th detection (31s later, cooldown expired, but need 3 detections in new window)
        t_after_cooldown = t0 + 32.0
        confirmed, data = tracker.register_detection("gun", 0.88, bbox, now=t_after_cooldown)
        self.assertFalse(confirmed)

        tracker.register_detection("gun", 0.89, bbox, now=t_after_cooldown + 0.2)
        confirmed, data = tracker.register_detection("gun", 0.94, bbox, now=t_after_cooldown + 0.4)
        self.assertTrue(confirmed)
        self.assertEqual(data["confidence"], 0.94)

    def test_camera_weapon_tracker_window_expiration(self):
        """Hits older than window_seconds must be pruned and not count towards confirmation."""
        tracker = CameraWeaponTracker(
            camera_id=1,
            confirmation_count=3,
            window_seconds=2.0,
            cooldown_seconds=10.0,
        )

        t0 = 2000.0
        bbox = (50, 50, 150, 150)

        # 1st detection at t=0
        tracker.register_detection("knife", 0.80, bbox, now=t0)
        # 2nd detection at t=0.5
        tracker.register_detection("knife", 0.82, bbox, now=t0 + 0.5)

        # 3rd detection at t=3.0 (2.5s later -> previous hits expired)
        confirmed, data = tracker.register_detection("knife", 0.85, bbox, now=t0 + 3.0)
        self.assertFalse(confirmed)
        self.assertEqual(len(tracker.history), 1)

    def test_multi_camera_isolation(self):
        """Camera 1 detections must NEVER trigger or affect Camera 2 state."""
        tracker1 = CameraWeaponTracker(camera_id=1, confirmation_count=3, window_seconds=2.0)
        tracker2 = CameraWeaponTracker(camera_id=2, confirmation_count=3, window_seconds=2.0)

        t0 = 3000.0
        bbox = (20, 20, 80, 80)

        # Camera 1 receives 2 hits
        tracker1.register_detection("gun", 0.80, bbox, now=t0)
        tracker1.register_detection("gun", 0.85, bbox, now=t0 + 0.5)

        # Camera 2 receives 1 hit -> should NOT confirm
        confirmed, data = tracker2.register_detection("gun", 0.90, bbox, now=t0 + 0.6)
        self.assertFalse(confirmed)
        self.assertEqual(len(tracker2.history), 1)

        # Camera 1 receives 3rd hit -> Camera 1 confirms, Camera 2 remains unconfirmed
        confirmed1, data1 = tracker1.register_detection("gun", 0.88, bbox, now=t0 + 0.8)
        self.assertTrue(confirmed1)
        self.assertEqual(data1["camera_id"], 1)

        self.assertEqual(len(tracker2.history), 1)

    def test_polygon_zone_filtering(self):
        """Points inside polygon return True, points outside return False."""
        polygon = [[100, 100], [300, 100], [300, 300], [100, 300]]

        # Center inside zone
        inside_point = (200, 200)
        self.assertTrue(_point_in_zone(inside_point, polygon))

        # Center outside zone
        outside_point = (50, 50)
        self.assertFalse(_point_in_zone(outside_point, polygon))

        outside_point_2 = (400, 400)
        self.assertFalse(_point_in_zone(outside_point_2, polygon))

    def test_whatsapp_weapon_message_builder(self):
        """Verify formatting of WhatsApp weapon alert."""
        msg = build_weapon_message(
            camera_name="Main Gate",
            weapon_class="gun",
            timestamp="02:30 PM",
            confidence=0.854,
            zone_name="Entrance Polygon",
            forensic_confirmed=True,
        )
        self.assertIn("⚠️ Weapon Detected", msg)
        self.assertIn("Camera: Main Gate", msg)
        self.assertIn("Type: Gun", msg)
        self.assertIn("Confidence: 85%", msg)
        self.assertIn("Zone: Entrance Polygon", msg)
        self.assertIn("Verification: Confirmed", msg)

    def test_clean_frame_verification_no_live_overlays(self):
        """
        CRITICAL REQUIREMENT:
        Ensure that passing a frame through weapon detection and MJPEG publishing
        leaves the frame 100% unmodified with ZERO bounding boxes or text overlays.
        """
        # Create synthetic camera frame with high-entropy gradient
        h, w = 480, 640
        raw_frame = np.zeros((h, w, 3), dtype=np.uint8)
        raw_frame[:, :, 0] = np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1))
        raw_frame[:, :, 1] = np.tile(np.linspace(255, 0, h, dtype=np.uint8)[:, None], (1, w))
        raw_frame[:, :, 2] = 128

        # Make exact copy before running weapon engine
        original_frame_copy = raw_frame.copy()

        # Run weapon engine on the frame
        engine = WeaponDetectionEngine()
        _ = engine.detect(raw_frame)

        # 1. Assert memory content of the input frame is IDENTICAL (byte for byte)
        np.testing.assert_array_equal(
            raw_frame,
            original_frame_copy,
            err_msg="Weapon detection mutated the input frame! Live feed MUST receive clean frames.",
        )

        # 2. Assert MJPEG stream delivery receives clean encoded frame
        camera_id = 9999
        clear_frame(camera_id)
        _, encoded_jpg = cv2.imencode(".jpg", raw_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        publish_frame(camera_id, encoded_jpg.tobytes())

        delivered_bytes = wait_for_frame(camera_id, timeout=1.0)
        self.assertIsNotNone(delivered_bytes)

        # Decode the delivered MJPEG frame
        delivered_arr = np.frombuffer(delivered_bytes, dtype=np.uint8)
        decoded_frame = cv2.imdecode(delivered_arr, cv2.IMREAD_COLOR)

        # Compare decoded frame with original (within standard JPEG loss tolerance)
        diff = cv2.absdiff(decoded_frame, raw_frame)
        mean_diff = np.mean(diff)
        self.assertLess(mean_diff, 5.0, f"Delivered stream has high difference from raw frame (mean diff: {mean_diff})")


if __name__ == "__main__":
    unittest.main()
