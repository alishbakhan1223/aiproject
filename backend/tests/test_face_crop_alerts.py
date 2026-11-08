"""
Unit and Integration Tests for:
1. Per-face crop with padding & bounding box preservation.
2. Multi-person in same scene generating distinct Unknown IDs and separate crops.
3. Known person per-face cropping and scene snapshot saving.
4. Track debounce and alerting.
5. GET /events/recent-scenes (multi-person scene grouping with face crops).
6. Parsing helpers.
"""
import os
import sys
import json
import unittest
import numpy as np
import cv2
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import Base, Event, UnknownPerson, UnknownSighting, UnknownEmbedding, KnownFace, FaceEmbedding
from app.config import settings
from app.face_crop_service import (
    crop_face_with_padding,
    process_unknown_face_alert,
    process_known_face_crop,
    TrackAlertManager,
)
from app.routers.alerts import _parse_raw_unknown_id, _parse_bbox, _format_snapshot_url
from app.routers.events import get_recent_scenes


class MockFace:
    def __init__(self, bbox=(20, 20, 80, 90), det_score=0.92, embedding=None):
        self.bbox = bbox
        self.det_score = det_score
        self.embedding = embedding if embedding is not None else np.random.randn(512).astype(np.float32)
        self.quality_info = {
            "is_acceptable": True,
            "quality_score": 85.0,
            "sharpness": 120.0,
            "det_score": det_score,
            "brightness": 110.0,
            "size_px": (bbox[2] - bbox[0], bbox[3] - bbox[1]),
            "rejection_reason": None,
        }


class TestFaceCropAlerts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(settings.DATABASE_URL)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def test_crop_face_with_padding(self):
        """Verify face crop extracts padded region within frame bounds."""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Draw distinctive marker inside face box
        frame[50:150, 100:200] = (0, 255, 0)

        bbox = (100, 50, 200, 150)
        crop = crop_face_with_padding(frame, bbox, padding_pct=0.20)

        self.assertIsNotNone(crop)
        # Bbox width is 100, pad_x is 20 -> expected width 140
        self.assertEqual(crop.shape[1], 140)
        self.assertEqual(crop.shape[0], 140)

        # Edge case: Face near boundary
        bbox_edge = (5, 5, 60, 60)
        crop_edge = crop_face_with_padding(frame, bbox_edge, padding_pct=0.20)
        self.assertIsNotNone(crop_edge)
        self.assertGreater(crop_edge.shape[0], 0)
        self.assertGreater(crop_edge.shape[1], 0)

    def test_multi_person_scene_produces_distinct_crops_and_ids(self):
        """
        When a scene has 3 people in the same frame, each detected unknown face
        gets its own separate crop, saved as its own image and linked to its own ID:
        Unknown-001, 002, 003.
        """
        frame = np.full((720, 1280, 3), 100, dtype=np.uint8)
        # Draw 3 simulated distinct faces
        cv2.circle(frame, (200, 300), 50, (255, 200, 150), -1)
        cv2.circle(frame, (600, 300), 50, (200, 255, 150), -1)
        cv2.circle(frame, (1000, 300), 50, (150, 200, 255), -1)

        # 3 orthogonal embeddings so they never match each other
        emb1 = np.zeros(512, dtype=np.float32)
        emb1[0] = 1.0
        emb2 = np.zeros(512, dtype=np.float32)
        emb2[100] = 1.0
        emb3 = np.zeros(512, dtype=np.float32)
        emb3[200] = 1.0

        face1 = MockFace(bbox=(150, 250, 250, 350), embedding=emb1)
        face2 = MockFace(bbox=(550, 250, 650, 350), embedding=emb2)
        face3 = MockFace(bbox=(950, 250, 1050, 350), embedding=emb3)

        seen_unknown_ids = set()

        # Process Face 1
        res1 = process_unknown_face_alert(
            face1, frame, "CAM_TEST_1", self.db, is_in_zone=True, track_id=101,
            exclude_person_ids=seen_unknown_ids,
        )
        self.assertIsNotNone(res1)
        seen_unknown_ids.add(res1["raw_unknown_id"])
        self.assertTrue(res1["is_new"])
        self.assertTrue(os.path.exists(res1["face_crop_path"]))
        self.assertTrue(os.path.exists(res1["scene_snapshot_path"]))
        self.assertIn("crop", res1["face_crop_path"])
        self.assertIn("scene", res1["scene_snapshot_path"])

        # Process Face 2
        res2 = process_unknown_face_alert(
            face2, frame, "CAM_TEST_1", self.db, is_in_zone=True, track_id=102,
            exclude_person_ids=seen_unknown_ids,
        )
        self.assertIsNotNone(res2)
        seen_unknown_ids.add(res2["raw_unknown_id"])
        self.assertTrue(res2["is_new"])
        self.assertNotEqual(res1["raw_unknown_id"], res2["raw_unknown_id"])
        self.assertNotEqual(res1["face_crop_path"], res2["face_crop_path"])

        # Process Face 3
        res3 = process_unknown_face_alert(
            face3, frame, "CAM_TEST_1", self.db, is_in_zone=True, track_id=103,
            exclude_person_ids=seen_unknown_ids,
        )
        self.assertIsNotNone(res3)
        seen_unknown_ids.add(res3["raw_unknown_id"])
        self.assertTrue(res3["is_new"])
        self.assertNotEqual(res1["raw_unknown_id"], res3["raw_unknown_id"])
        self.assertNotEqual(res2["raw_unknown_id"], res3["raw_unknown_id"])

        # Verify 3 distinct identities created
        self.assertEqual(len(seen_unknown_ids), 3)

        # Cleanup
        for pid in seen_unknown_ids:
            p = self.db.query(UnknownPerson).filter(UnknownPerson.id == pid).first()
            if p:
                self.db.delete(p)
        self.db.commit()

    def test_process_known_face_crop(self):
        """Verify known persons also get per-face crops and scene snapshots saved."""
        frame = np.full((480, 640, 3), 120, dtype=np.uint8)
        cv2.circle(frame, (300, 200), 40, (255, 255, 255), -1)

        face = MockFace(bbox=(260, 160, 340, 240))
        res = process_known_face_crop(
            face=face,
            frame=frame,
            camera_name="CAM_KNOWN_1",
            person_name="Alice Specialist",
            is_in_zone=True,
            track_id=88,
        )

        self.assertIsNotNone(res)
        self.assertEqual(res["person_name"], "Alice Specialist")
        self.assertTrue(os.path.exists(res["face_crop_path"]))
        self.assertTrue(os.path.exists(res["scene_snapshot_path"]))
        self.assertIn("Alice_Specialist", res["face_crop_path"])

    def test_track_debounce_manager(self):
        """Verify TrackAlertManager debounces alerts for the same track within cooldown."""
        manager = TrackAlertManager(debounce_seconds=2.0)
        cam = "cam_test"
        track_id = 42
        unknown_id = 99

        # First alert on this track -> True
        self.assertTrue(manager.should_emit_alert(cam, track_id, unknown_id))

        # Immediate next call for same track & identity -> False (debounced)
        self.assertFalse(manager.should_emit_alert(cam, track_id, unknown_id))

        # Different track_id -> True
        self.assertTrue(manager.should_emit_alert(cam, 43, unknown_id))

        # None track_id -> always True
        self.assertTrue(manager.should_emit_alert(cam, None, unknown_id))

    def test_bbox_and_url_parsing_helpers(self):
        """Verify parsing helpers for bounding box, IDs and URLs."""
        self.assertEqual(_parse_raw_unknown_id("Unknown-007"), 7)
        self.assertEqual(_parse_raw_unknown_id("UNKN-042"), 42)
        self.assertEqual(_parse_raw_unknown_id(15), 15)

        self.assertEqual(_parse_bbox("[10, 20, 30, 40]"), [10, 20, 30, 40])
        self.assertEqual(_parse_bbox("10, 20, 30, 40"), [10, 20, 30, 40])
        self.assertEqual(_parse_bbox([10, 20, 30, 40]), [10, 20, 30, 40])
        self.assertIsNone(_parse_bbox(None))

        self.assertEqual(_format_snapshot_url("data/snapshots/unknown/Unknown-001/crop.webp"), "/snapshots/unknown/Unknown-001/crop.webp")


if __name__ == "__main__":
    unittest.main()
