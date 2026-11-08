"""
Unit tests for:
1. Bug 1: Snapshot folder routing for known faces vs weapon/misc.
2. Feature 2: Remove photo back to Unknown-NNN with exact ID tracking and sequence handling.
3. Feature 3: Unknown deactualization sweep.
4. Part A: Face quality evaluation, blur gating, and max-quality cover selection.
5. Part C: Weapon detection distinct knife & gun classes and multi-scale NMS fusion.
"""
import os
import sys
import unittest
import numpy as np
import cv2
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models import Base, KnownFace, FaceEmbedding, UnknownPerson, UnknownSighting, UnknownEmbedding, Event
from app.config import settings
from app.face_quality import evaluate_face_quality, _variance_of_laplacian
from app.unknown_person_service import (
    _known_folder,
    _unknown_folder,
    promote_to_known,
    remove_photo_to_unknown,
    revert_to_unknown,
    resolve_unknown_person,
)
from app.unknown_deactualization import _sweep_once
from app.weapon_engine import WeaponDetectionEngine, CameraWeaponTracker


class DummyFace:
    def __init__(self, bbox=(10, 10, 100, 100), det_score=0.95, pose=(2.0, 3.0, 1.0)):
        self.bbox = bbox
        self.det_score = det_score
        self.pose = pose
        self.embedding = np.random.randn(512).astype(np.float32)


class TestUnknownAndRoutingFeatures(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(settings.DATABASE_URL)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def test_known_folder_routing_format(self):
        """Known face snapshots must route to data/snapshots/known/<person_name>/"""
        folder = _known_folder("Alishba Khan")
        self.assertTrue(folder.endswith("data/snapshots/known/Alishba Khan") or folder.endswith("data\\snapshots\\known\\Alishba Khan"))
        self.assertNotIn("weapon", folder)

    def test_unknown_folder_routing_format(self):
        """Unknown person snapshots must route to data/snapshots/unknown/Unknown-NNN"""
        folder = _unknown_folder(7)
        self.assertTrue(folder.endswith("data/snapshots/unknown/Unknown-007") or folder.endswith("data\\snapshots\\unknown\\Unknown-007"))
        self.assertNotIn("weapon", folder)

    def test_face_quality_evaluation_sharp_vs_blurry(self):
        """Verify quality score calculation: sharp face is acceptable, heavy blur is rejected."""
        # Sharp synthetic crop
        sharp_frame = np.zeros((200, 200, 3), dtype=np.uint8)
        cv2.putText(sharp_frame, "HIGH CONTRAST SHARP", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        face_sharp = DummyFace(bbox=(5, 5, 150, 150), det_score=0.95)

        res_sharp = evaluate_face_quality(sharp_frame, face_sharp)
        self.assertTrue(res_sharp["is_acceptable"])
        self.assertGreater(res_sharp["quality_score"], 40.0)

        # Blurry synthetic crop (uniform black / Gaussian blurred)
        blurry_frame = np.full((200, 200, 3), 120, dtype=np.uint8)
        face_blurry = DummyFace(bbox=(5, 5, 150, 150), det_score=0.95)

        res_blurry = evaluate_face_quality(blurry_frame, face_blurry)
        self.assertFalse(res_blurry["is_acceptable"])
        self.assertIsNotNone(res_blurry["rejection_reason"])

    def test_max_quality_cover_selection(self):
        """Representative / cover snapshot must track highest quality score."""
        dummy_vector = [0.1] * 512
        now = datetime.utcnow()
        dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)

        # First sighting with quality 50
        person, is_new = resolve_unknown_person(dummy_vector, dummy_frame, self.db, "cam1", quality_score=50.0)
        self.assertTrue(is_new)
        first_cover = person.representative_snapshot_path

        # Second sighting with higher quality 85 -> updates cover
        person2, is_new2 = resolve_unknown_person(dummy_vector, dummy_frame, self.db, "cam1", quality_score=85.0)
        self.assertFalse(is_new2)
        second_cover = person2.representative_snapshot_path
        self.assertNotEqual(first_cover, second_cover)

        # Third sighting with lower quality 45 -> does NOT downgrade cover
        person3, is_new3 = resolve_unknown_person(dummy_vector, dummy_frame, self.db, "cam1", quality_score=45.0)
        self.assertFalse(is_new3)
        self.assertEqual(person3.representative_snapshot_path, second_cover)

        # Cleanup
        self.db.delete(person)
        self.db.commit()

    def test_promote_records_source_unknown_id_and_remove_restores_exact_id(self):
        """
        Verify the complete workflow:
        1. Create UnknownPerson(id=999) with dummy embedding & snapshot
        2. promote_to_known() assigns source_unknown_id = 999 on FaceEmbedding
        3. UnknownPerson(id=999) is deleted upon promotion
        4. remove_photo_to_unknown() restores with exact Unknown-999 id!
        """
        test_unknown_id = 991
        existing = self.db.query(UnknownPerson).filter(UnknownPerson.id == test_unknown_id).first()
        if existing:
            self.db.delete(existing)
            self.db.commit()

        dummy_vector = [0.1] * 512
        now = datetime.utcnow()
        unknown = UnknownPerson(
            id=test_unknown_id,
            reference_embedding=dummy_vector,
            first_seen=now,
            last_seen=now,
            status="active",
        )
        self.db.add(unknown)
        self.db.flush()

        unknown_dir = _unknown_folder(test_unknown_id)
        os.makedirs(unknown_dir, exist_ok=True)
        dummy_file = os.path.join(unknown_dir, "test_shot.jpg")
        with open(dummy_file, "wb") as f:
            f.write(b"dummy image content")

        unknown.representative_snapshot_path = dummy_file
        self.db.add(UnknownSighting(
            unknown_person_id=test_unknown_id,
            camera_name="test_cam",
            snapshot_path=dummy_file,
            quality_score=75.0,
            timestamp=now,
        ))
        self.db.add(UnknownEmbedding(
            unknown_person_id=test_unknown_id,
            vector=dummy_vector,
            snapshot_path=dummy_file,
            quality_score=75.0,
            created_at=now,
        ))
        self.db.commit()

        # Promote to known
        known = promote_to_known(test_unknown_id, "Test Unit Subject", self.db)
        self.assertIsNotNone(known)
        self.assertEqual(known.name, "Test Unit Subject")

        # Check that FaceEmbedding has source_unknown_id and quality_score
        emb = self.db.query(FaceEmbedding).filter(FaceEmbedding.face_id == known.id).first()
        self.assertIsNotNone(emb)
        self.assertEqual(emb.source_unknown_id, test_unknown_id)

        # Check that original unknown row was deleted
        old_unknown = self.db.query(UnknownPerson).filter(UnknownPerson.id == test_unknown_id).first()
        self.assertIsNone(old_unknown)

        # Create an Event linked to this known face to verify FK safety
        test_event = Event(
            event_type="known_person",
            camera_name="test_cam",
            timestamp=now,
            person_name="Test Unit Subject",
            known_face_id=known.id,
        )
        self.db.add(test_event)
        self.db.commit()
        event_id = test_event.id

        # Remove photo back to unknown
        res = remove_photo_to_unknown(emb.id, self.db)
        self.assertEqual(res["id"], test_unknown_id)
        self.assertEqual(res["label"], f"Unknown-{test_unknown_id:03d}")
        self.assertTrue(res["restored_to_original"])

        # Check that UnknownPerson exists again with the exact same ID
        restored_unknown = self.db.query(UnknownPerson).filter(UnknownPerson.id == test_unknown_id).first()
        self.assertIsNotNone(restored_unknown)
        self.assertEqual(restored_unknown.id, test_unknown_id)
        self.assertEqual(restored_unknown.status, "active")

        # Check that KnownFace was removed (since 0 photos left), but Event still exists with NULL FK
        recheck_known = self.db.query(KnownFace).filter(KnownFace.id == known.id).first()
        self.assertIsNone(recheck_known)

        recheck_event = self.db.query(Event).filter(Event.id == event_id).first()
        self.assertIsNotNone(recheck_event)
        self.assertIsNone(recheck_event.known_face_id)
        self.assertEqual(recheck_event.person_name, "Test Unit Subject")

        # Cleanup
        self.db.delete(recheck_event)
        self.db.delete(restored_unknown)
        self.db.commit()

    def test_legacy_photo_remove_to_new_unknown(self):
        """When source_unknown_id is NULL, remove_photo_to_unknown creates a new UnknownPerson and flags restored_to_original=False."""
        known = KnownFace(name="Test Legacy Person")
        self.db.add(known)
        self.db.flush()

        emb = FaceEmbedding(
            face_id=known.id,
            vector=[0.2] * 512,
            source_unknown_id=None,
            photo_path=None,
            quality_score=60.0,
            added_at=datetime.utcnow(),
        )
        self.db.add(emb)
        self.db.commit()
        self.db.refresh(emb)

        res = remove_photo_to_unknown(emb.id, self.db)
        self.assertFalse(res["restored_to_original"])
        self.assertIsNotNone(res["id"])

        created_unknown = self.db.query(UnknownPerson).filter(UnknownPerson.id == res["id"]).first()
        if created_unknown:
            self.db.delete(created_unknown)
            self.db.commit()

    def test_deactualization_sweep(self):
        """Sweep marks active unknowns older than timeout as inactive."""
        stale_time = datetime.utcnow() - timedelta(seconds=settings.UNKNOWN_INACTIVITY_TIMEOUT_SECONDS + 10)
        stale_person = UnknownPerson(
            reference_embedding=[0.3] * 512,
            first_seen=stale_time,
            last_seen=stale_time,
            status="active",
        )
        self.db.add(stale_person)
        self.db.commit()
        self.db.refresh(stale_person)

        _sweep_once()

        self.db.refresh(stale_person)
        self.assertEqual(stale_person.status, "inactive")

        self.db.delete(stale_person)
        self.db.commit()

    def test_weapon_canonical_classes(self):
        """Gun and knife must be mapped to distinct canonical classes."""
        engine = WeaponDetectionEngine.__new__(WeaponDetectionEngine)
        self.assertEqual(engine.canonical_label("handgun"), "Gun")
        self.assertEqual(engine.canonical_label("pistol"), "Gun")
        self.assertEqual(engine.canonical_label("assault rifle"), "Gun")
        self.assertEqual(engine.canonical_label("knife"), "Knife")
        self.assertEqual(engine.canonical_label("dagger"), "Knife")
        self.assertEqual(engine.canonical_label("blade"), "Knife")


if __name__ == "__main__":
    unittest.main()
