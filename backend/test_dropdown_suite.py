import os
import sys
import shutil
import requests
import numpy as np
from datetime import datetime, timedelta, timezone

# Ensure we are in backend dir
if os.path.exists("app"):
    sys.path.insert(0, ".")
    SNAP_DIR = os.path.abspath("data/snapshots")
else:
    sys.path.insert(0, "backend")
    SNAP_DIR = os.path.abspath("backend/data/snapshots")

from app.database import SessionLocal
from app.models import (
    KnownFace, FaceEmbedding, UnknownPerson, UnknownSighting,
    UnknownEmbedding, Event, User, Camera
)
from app.auth import create_access_token
from app.spec_actualization_service import PKT
from sqlalchemy import text, func

BASE_URL = "http://127.0.0.1:8000"
TOKEN = create_access_token("admin")
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

print("==================================================")
print("  RUNNING VERIFICATION TESTS FOR DROPDOWN MAPPING ")
print("==================================================")

db = SessionLocal()

# Record baseline counts
tables = [
    'actualization', 'cameras', 'companies', 'events',
    'face_embeddings', 'known_faces', 'locations',
    'unknown_embeddings', 'unknown_persons', 'unknown_sightings',
    'unknowns', 'users', 'zones'
]
baseline = {}
for t in tables:
    cnt = db.execute(text(f"SELECT count(*) FROM {t}")).scalar()
    baseline[t] = cnt

print("Baseline row counts:", baseline)

def get_snapshot_counts():
    counts = {}
    for sub in ["known", "unknown", "old_pictures"]:
        p = os.path.join(SNAP_DIR, sub)
        top = len([f for f in os.listdir(p) if os.path.isfile(os.path.join(p, f))]) if os.path.exists(p) else 0
        all_cnt = 0
        for root, dirs, files in os.walk(p):
            all_cnt += len(files)
        counts[sub] = (top, all_cnt)
    return counts

baseline_snaps = get_snapshot_counts()
print("Baseline snapshots:", baseline_snaps)

try:
    # ---------------------------------------------------------
    # TEST 1: Dropdown listing all known persons, sorted, photo counts
    # ---------------------------------------------------------
    print("\n--- TEST 1: Dropdown listing all known persons ---")
    r1 = requests.get(f"{BASE_URL}/known-faces", headers=HEADERS)
    assert r1.status_code == 200, f"Expected 200, got {r1.status_code}"
    faces = r1.json()
    names = [f["name"] for f in faces]
    print(f"Loaded {len(faces)} known faces: {names}")
    for f in faces:
        count = f.get('photo_count', 0)
        label = f"{f['name']} ({count}/4 photos, oldest photo will be replaced)" if count >= 4 else f"{f['name']} ({count}/4 photos)"
        print(f"  - {label}")

    # Verify placeholder blocks submission (empty name without known_face_id returns 400)
    r_empty = requests.post(
        f"{BASE_URL}/unknown-persons/999999/convert-to-known",
        json={"name": ""},
        headers=HEADERS
    )
    assert r_empty.status_code in (400, 422), f"Expected 400/422 on empty, got {r_empty.status_code}"
    print("Test 1 Result: PASS (Known persons loaded, photo counts formatted, empty selection blocked)")

    # ---------------------------------------------------------
    # TEST 2: Mapping a TEST unknown to an existing TEST person
    # ---------------------------------------------------------
    print("\n--- TEST 2: Mapping TEST unknown to existing TEST person ---")
    now_pkt = datetime.now(PKT).replace(tzinfo=None)
    dummy_vec = [0.01] * 512

    # Create dummy snapshot
    test_known_dir = os.path.join(SNAP_DIR, "known", "TEST_PERSON_A")
    os.makedirs(test_known_dir, exist_ok=True)
    snap_a1 = os.path.join(test_known_dir, "test_1.jpg")
    with open(snap_a1, "wb") as f:
        f.write(b"dummy_test_known_a")

    kf_a = KnownFace(name="TEST_PERSON_A", photo_path=snap_a1)
    db.add(kf_a)
    db.commit()
    db.refresh(kf_a)

    emb_a = FaceEmbedding(
        face_id=kf_a.id,
        photo_path=snap_a1,
        vector=dummy_vec,
        quality_score=0.90,
        added_at=now_pkt,
    )
    db.add(emb_a)
    db.commit()

    # Create dummy unknown person
    test_u1_dir = os.path.join(SNAP_DIR, "unknown", "Unknown-991")
    os.makedirs(test_u1_dir, exist_ok=True)
    snap_u1 = os.path.join(test_u1_dir, "snap1.webp")
    with open(snap_u1, "wb") as f:
        f.write(b"dummy_test_unknown_1")

    up1 = UnknownPerson(
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        representative_snapshot_path=snap_u1,
        status="active"
    )
    db.add(up1)
    db.commit()
    db.refresh(up1)

    ue1 = UnknownEmbedding(
        unknown_person_id=up1.id,
        vector=dummy_vec,
        snapshot_path=snap_u1,
        quality_score=0.88,
        created_at=datetime.utcnow()
    )
    us1 = UnknownSighting(
        unknown_person_id=up1.id,
        camera_name="TestCam",
        snapshot_path=snap_u1,
        quality_score=0.88,
        timestamp=datetime.utcnow()
    )
    db.add(ue1)
    db.add(us1)

    # Insert into unknowns table
    db.execute(text("""
        INSERT INTO unknowns (unknown_id, company_code, location_code, camera_code, insight_id, date_time, unknown_creation_number)
        VALUES (:uid, '001', '001', '001', :iid, :dt, 991)
    """), {
        "uid": "UNKN001001001103026991",
        "iid": f"unknown-person-{up1.id}",
        "dt": now_pkt
    })
    db.commit()

    # Call convert-to-known with known_face_id and name
    r2 = requests.post(
        f"{BASE_URL}/unknown-persons/{up1.id}/convert-to-known",
        json={"known_face_id": kf_a.id, "name": kf_a.name},
        headers=HEADERS
    )
    assert r2.status_code == 200, f"Expected 200, got {r2.status_code}: {r2.text}"
    res2 = r2.json()
    print("Map response:", res2)
    assert res2["photo_count"] == 2, f"Expected 2 photos, got {res2['photo_count']}"

    # Verify actualization row
    act_row = db.execute(text("""
        SELECT unkn_id, user_code, status, known_id, known_date
        FROM actualization WHERE unkn_id = 'UNKN001001001103026991'
    """)).first()
    assert act_row is not None, "actualization row not created!"
    print(f"actualization row: {dict(act_row._mapping)}")
    assert act_row.status == "Successful", f"Expected Successful, got {act_row.status}"
    assert act_row.known_id == kf_a.id, f"Expected known_id {kf_a.id}, got {act_row.known_id}"

    print("Test 2 Result: PASS (Mapped to existing person, photo added, actualization row created)")

    # ---------------------------------------------------------
    # TEST 3: Person with 4/4 photos, FIFO eviction & archive
    # ---------------------------------------------------------
    print("\n--- TEST 3: Person with 4/4 photos, FIFO eviction & archive ---")
    test_b_dir = os.path.join(SNAP_DIR, "known", "TEST_PERSON_B")
    os.makedirs(test_b_dir, exist_ok=True)
    snap_b_files = []
    for i in range(4):
        p = os.path.join(test_b_dir, f"test_{i+1}.jpg")
        with open(p, "wb") as f:
            f.write(f"dummy_b_{i+1}".encode())
        snap_b_files.append(p)

    kf_b = KnownFace(name="TEST_PERSON_B", photo_path=snap_b_files[0])
    db.add(kf_b)
    db.commit()
    db.refresh(kf_b)

    for i, p in enumerate(snap_b_files):
        emb = FaceEmbedding(
            face_id=kf_b.id,
            photo_path=p,
            vector=dummy_vec,
            quality_score=0.80 + (i * 0.02),
            added_at=now_pkt - timedelta(hours=(4 - i)),
        )
        db.add(emb)
    db.commit()

    # Verify GET /known-faces reflects 4/4 photos
    r_b_check = requests.get(f"{BASE_URL}/known-faces", headers=HEADERS)
    b_info = [f for f in r_b_check.json() if f["id"] == kf_b.id][0]
    print(f"TEST_PERSON_B photo count before mapping: {b_info['photo_count']}/4")
    assert b_info["photo_count"] == 4, "Expected 4 photos before mapping"

    # Create unknown to map into TEST_PERSON_B
    test_u2_dir = os.path.join(SNAP_DIR, "unknown", "Unknown-992")
    os.makedirs(test_u2_dir, exist_ok=True)
    snap_u2 = os.path.join(test_u2_dir, "snap2.webp")
    with open(snap_u2, "wb") as f:
        f.write(b"dummy_test_unknown_2")

    up2 = UnknownPerson(
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        representative_snapshot_path=snap_u2,
        status="active"
    )
    db.add(up2)
    db.commit()
    db.refresh(up2)

    ue2 = UnknownEmbedding(
        unknown_person_id=up2.id,
        vector=dummy_vec,
        snapshot_path=snap_u2,
        quality_score=0.95,
        created_at=datetime.utcnow()
    )
    us2 = UnknownSighting(
        unknown_person_id=up2.id,
        camera_name="TestCam",
        snapshot_path=snap_u2,
        quality_score=0.95,
        timestamp=datetime.utcnow()
    )
    db.add(ue2)
    db.add(us2)

    db.execute(text("""
        INSERT INTO unknowns (unknown_id, company_code, location_code, camera_code, insight_id, date_time, unknown_creation_number)
        VALUES (:uid, '001', '001', '001', :iid, :dt, 992)
    """), {
        "uid": "UNKN001001001103026992",
        "iid": f"unknown-person-{up2.id}",
        "dt": now_pkt
    })
    db.commit()

    # Map to TEST_PERSON_B (which has 4/4 photos)
    r3 = requests.post(
        f"{BASE_URL}/unknown-persons/{up2.id}/convert-to-known",
        json={"known_face_id": kf_b.id, "name": kf_b.name},
        headers=HEADERS
    )
    assert r3.status_code == 200, f"Expected 200, got {r3.status_code}: {r3.text}"
    res3 = r3.json()
    print("Map response (4/4 full):", res3)
    assert res3["photo_count"] == 4, f"Photo count should remain capped at 4, got {res3['photo_count']}"

    # Verify FIFO eviction archived into actualization
    act_b = db.execute(text("""
        SELECT unkn_id, old_picture, old_embedding IS NOT NULL as has_vec
        FROM actualization WHERE unkn_id = 'UNKN001001001103026992'
    """)).first()
    assert act_b is not None, "actualization row for UNKN...992 not found"
    print(f"actualization FIFO archive row: {dict(act_b._mapping)}")
    assert act_b.old_picture, "old_picture must be set on FIFO eviction"
    print("Test 3 Result: PASS (FIFO eviction archived oldest photo into actualization.old_picture)")

    # ---------------------------------------------------------
    # TEST 4: "+ Create new person..." & Case-insensitive Duplicate Mapping
    # ---------------------------------------------------------
    print("\n--- TEST 4: Create new person & Duplicate name handling ---")
    test_u3_dir = os.path.join(SNAP_DIR, "unknown", "Unknown-993")
    os.makedirs(test_u3_dir, exist_ok=True)
    snap_u3 = os.path.join(test_u3_dir, "snap3.webp")
    with open(snap_u3, "wb") as f:
        f.write(b"dummy_test_unknown_3")

    up3 = UnknownPerson(
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        representative_snapshot_path=snap_u3,
        status="active"
    )
    db.add(up3)
    db.commit()
    db.refresh(up3)
    db.add(UnknownEmbedding(unknown_person_id=up3.id, vector=dummy_vec, snapshot_path=snap_u3, quality_score=0.91))
    db.add(UnknownSighting(unknown_person_id=up3.id, camera_name="TestCam", snapshot_path=snap_u3, quality_score=0.91))
    db.execute(text("""
        INSERT INTO unknowns (unknown_id, company_code, location_code, camera_code, insight_id, date_time, unknown_creation_number)
        VALUES ('UNKN001001001103026993', '001', '001', '001', :iid, :dt, 993)
    """), {"iid": f"unknown-person-{up3.id}", "dt": now_pkt})
    db.commit()

    # Create new person "TEST_PERSON_C"
    r4_new = requests.post(
        f"{BASE_URL}/unknown-persons/{up3.id}/convert-to-known",
        json={"name": "TEST_PERSON_C"},
        headers=HEADERS
    )
    assert r4_new.status_code == 200, f"Expected 200, got {r4_new.status_code}: {r4_new.text}"
    kf_c = db.query(KnownFace).filter(KnownFace.name == "TEST_PERSON_C").first()
    assert kf_c is not None, "TEST_PERSON_C not created!"
    print("Created new person:", kf_c.name, "ID:", kf_c.id)

    # Now test duplicate name with different casing "test_person_c"
    test_u4_dir = os.path.join(SNAP_DIR, "unknown", "Unknown-994")
    os.makedirs(test_u4_dir, exist_ok=True)
    snap_u4 = os.path.join(test_u4_dir, "snap4.webp")
    with open(snap_u4, "wb") as f:
        f.write(b"dummy_test_unknown_4")

    up4 = UnknownPerson(
        first_seen=datetime.utcnow(),
        last_seen=datetime.utcnow(),
        representative_snapshot_path=snap_u4,
        status="active"
    )
    db.add(up4)
    db.commit()
    db.refresh(up4)
    db.add(UnknownEmbedding(unknown_person_id=up4.id, vector=dummy_vec, snapshot_path=snap_u4, quality_score=0.89))
    db.add(UnknownSighting(unknown_person_id=up4.id, camera_name="TestCam", snapshot_path=snap_u4, quality_score=0.89))
    db.execute(text("""
        INSERT INTO unknowns (unknown_id, company_code, location_code, camera_code, insight_id, date_time, unknown_creation_number)
        VALUES ('UNKN001001001103026994', '001', '001', '001', :iid, :dt, 994)
    """), {"iid": f"unknown-person-{up4.id}", "dt": now_pkt})
    db.commit()

    r4_dup = requests.post(
        f"{BASE_URL}/unknown-persons/{up4.id}/convert-to-known",
        json={"name": "test_person_c"},
        headers=HEADERS
    )
    assert r4_dup.status_code == 200, f"Expected 200, got {r4_dup.status_code}: {r4_dup.text}"
    all_c = db.query(KnownFace).filter(func.lower(KnownFace.name) == "test_person_c").all()
    assert len(all_c) == 1, f"Expected exactly 1 person (no duplicate), found {len(all_c)}"
    assert len(all_c[0].embeddings) == 2, f"Expected 2 photos on TEST_PERSON_C, got {len(all_c[0].embeddings)}"
    print("Test 4 Result: PASS (New person created, duplicate name mapped to existing person without creating duplicate)")

    # ---------------------------------------------------------
    # TEST 5: Server error on >30-day window in English
    # ---------------------------------------------------------
    print("\n--- TEST 5: Mapping window >30-day error in English ---")
    test_u5_dir = os.path.join(SNAP_DIR, "unknown", "Unknown-995")
    os.makedirs(test_u5_dir, exist_ok=True)
    snap_u5 = os.path.join(test_u5_dir, "snap5.webp")
    with open(snap_u5, "wb") as f:
        f.write(b"dummy_test_unknown_5")

    old_dt = now_pkt - timedelta(days=35)
    up5 = UnknownPerson(
        first_seen=old_dt,
        last_seen=old_dt,
        representative_snapshot_path=snap_u5,
        status="active"
    )
    db.add(up5)
    db.commit()
    db.refresh(up5)
    db.add(UnknownEmbedding(unknown_person_id=up5.id, vector=dummy_vec, snapshot_path=snap_u5, quality_score=0.90, created_at=old_dt))
    db.add(UnknownSighting(unknown_person_id=up5.id, camera_name="TestCam", snapshot_path=snap_u5, quality_score=0.90, timestamp=old_dt))
    db.execute(text("""
        INSERT INTO unknowns (unknown_id, company_code, location_code, camera_code, insight_id, date_time, unknown_creation_number)
        VALUES ('UNKN001001001103026995', '001', '001', '001', :iid, :dt, 995)
    """), {"iid": f"unknown-person-{up5.id}", "dt": old_dt})
    db.commit()

    r5 = requests.post(
        f"{BASE_URL}/unknown-persons/{up5.id}/convert-to-known",
        json={"name": "TEST_PERSON_A"},
        headers=HEADERS
    )
    print("Expired mapping response:", r5.status_code, r5.text)
    assert r5.status_code == 400, f"Expected 400 for expired, got {r5.status_code}"
    err_detail = r5.json().get("detail", "")
    assert "Mapping window closed: 30 days have passed." in err_detail, f"Expected English closed message, got {err_detail}"
    print("Test 5 Result: PASS (Server error returned in English: 'Mapping window closed: 30 days have passed.')")

finally:
    # ---------------------------------------------------------
    # CLEANUP: Delete ALL TEST_ rows and files
    # ---------------------------------------------------------
    print("\n--- CLEANUP: Deleting all TEST_ records and files ---")
    db.rollback()
    # Delete test actualization rows
    db.execute(text("DELETE FROM actualization WHERE unkn_id LIKE 'UNKN00100100110302699%'"))
    # Delete test unknowns
    db.execute(text("DELETE FROM unknowns WHERE unknown_id LIKE 'UNKN00100100110302699%'"))
    # Delete test embeddings & sightings
    db.execute(text("DELETE FROM unknown_sightings WHERE unknown_person_id IN (SELECT id FROM unknown_persons WHERE representative_snapshot_path LIKE '%Unknown-99%')"))
    db.execute(text("DELETE FROM unknown_embeddings WHERE unknown_person_id IN (SELECT id FROM unknown_persons WHERE representative_snapshot_path LIKE '%Unknown-99%')"))
    db.execute(text("DELETE FROM unknown_persons WHERE representative_snapshot_path LIKE '%Unknown-99%'"))

    # Delete test known faces and their embeddings
    db.execute(text("DELETE FROM face_embeddings WHERE face_id IN (SELECT id FROM known_faces WHERE name LIKE 'TEST_PERSON%')"))
    db.execute(text("DELETE FROM known_faces WHERE name LIKE 'TEST_PERSON%'"))
    db.commit()

    # Clean up disk files and directories
    for sub in ["Unknown-991", "Unknown-992", "Unknown-993", "Unknown-994", "Unknown-995"]:
        d = os.path.join(SNAP_DIR, "unknown", sub)
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)

    for k in ["TEST_PERSON_A", "TEST_PERSON_B", "TEST_PERSON_C"]:
        d = os.path.join(SNAP_DIR, "known", k)
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)

    # Check for any created files in old_pictures
    old_pic_dir = os.path.join(SNAP_DIR, "old_pictures")
    if os.path.exists(old_pic_dir):
        for f in os.listdir(old_pic_dir):
            if "test_" in f.lower() or "snap" in f.lower():
                try:
                    os.remove(os.path.join(old_pic_dir, f))
                except Exception:
                    pass

    print("Cleanup completed.")

    # ---------------------------------------------------------
    # TEST 6: Verify Row counts of ALL tables and snapshot counts
    # ---------------------------------------------------------
    print("\n--- TEST 6: Row counts and snapshot verification ---")
    after_counts = {}
    for t in tables:
        cnt = db.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        after_counts[t] = cnt

    print("Baseline counts:", baseline)
    print("After counts:   ", after_counts)

    mismatches = []
    for t in tables:
        if baseline[t] != after_counts[t]:
            mismatches.append((t, baseline[t], after_counts[t]))

    assert len(mismatches) == 0, f"Table row count mismatches detected: {mismatches}"

    after_snaps = get_snapshot_counts()
    print("Baseline snapshots:", baseline_snaps)
    print("After snapshots:   ", after_snaps)
    assert baseline_snaps == after_snaps, f"Snapshot count mismatch: {baseline_snaps} vs {after_snaps}"

    print("Test 6 Result: PASS (All 13 table row counts and snapshot file counts are 100% identical!)")

    db.close()

print("\n==================================================")
print("  ALL 6 TESTS PASSED SUCCESSFULLY!                ")
print("==================================================")
