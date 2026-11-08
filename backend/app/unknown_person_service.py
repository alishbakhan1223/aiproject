"""
Centralized unknown-person de-duplication + conversion service with quality-based cover selection.

Each distinct Unknown identity gets exactly ONE dedicated folder:
    data/snapshots/unknown/Unknown-001/snapshot_<timestamp>.webp
    data/snapshots/unknown/Unknown-001/snapshot_<timestamp>.webp
    ...
The representative/cover photo shown for an Unknown identity or Known person
is always the HIGHEST-QUALITY (sharpest, clearest) photo on file.

When a known person already has MAX_FACE_IMAGES photos and a new unknown is promoted,
the oldest known photo is NOT deleted: it is archived in data/snapshots/old/<known_id>/
and saved in the `actualization` table (old_* columns). It is restored automatically
when the promoted photo is removed back to unknown, or the whole person is reverted.
"""
import os
import time
import shutil
import cv2
import numpy as np
from datetime import datetime, timedelta, timezone
PKT = timezone(timedelta(hours=5))
from sqlalchemy import text, select, func
from sqlalchemy.orm import Session

from app.models import UnknownPerson, UnknownEmbedding, UnknownSighting, KnownFace, FaceEmbedding
from app.config import settings
from app.face_quality import _variance_of_laplacian

_DEDUP_LOCK_KEY = 913_223_001
MAX_FACE_IMAGES = 4


def _cosine_distance(embedding: np.ndarray, stored_vector) -> float:
    stored = np.array(stored_vector, dtype=np.float32)
    cos_sim = np.dot(embedding, stored) / (
        np.linalg.norm(embedding) * np.linalg.norm(stored) + 1e-8
    )
    return float(1 - cos_sim)


def _nearest_by_sighting_embeddings(embedding: np.ndarray, db: Session, exclude_person_ids: set = None):
    stmt = select(UnknownEmbedding)
    if exclude_person_ids:
        stmt = stmt.where(UnknownEmbedding.unknown_person_id.notin_(exclude_person_ids))
    row = db.execute(
        stmt
        .order_by(UnknownEmbedding.vector.cosine_distance(embedding))
        .limit(1)
    ).scalars().first()
    if row is None:
        return None, None
    return row.unknown_person_id, _cosine_distance(embedding, row.vector)


def _nearest_by_reference_embedding(embedding: np.ndarray, db: Session, exclude_person_ids: set = None):
    stmt = select(UnknownPerson)
    if exclude_person_ids:
        stmt = stmt.where(UnknownPerson.id.notin_(exclude_person_ids))
    row = db.execute(
        stmt
        .order_by(UnknownPerson.reference_embedding.cosine_distance(embedding))
        .limit(1)
    ).scalars().first()
    if row is None:
        return None, None
    return row.id, _cosine_distance(embedding, row.reference_embedding)


def _unknown_folder(unknown_id: int) -> str:
    return f"{settings.SNAPSHOT_DIR}/unknown/Unknown-{unknown_id:03d}"


def _known_folder(person_name: str) -> str:
    return f"{settings.SNAPSHOT_DIR}/known/{person_name.strip()}"


def _score_snapshot(path: str) -> float:
    """Computes Laplacian variance sharpness score of a snapshot on disk."""
    if not path or not os.path.exists(path):
        return -1.0
    frame = cv2.imread(path)
    if frame is None:
        return -1.0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return round(_variance_of_laplacian(gray), 2)


# ---------------------------------------------------------------------------
# Old-photo archive / restore helpers (actualization.old_* columns)
# ---------------------------------------------------------------------------
def _vec_to_list(v):
    if v is None:
        return None
    if isinstance(v, str):
        return [float(x) for x in v.strip("[] ").split(",") if x.strip()]
    return [float(x) for x in v]


def _vec_to_str(v):
    return "[" + ",".join(str(float(x)) for x in v) + "]"


def _archive_old_photo(oldest, known_face_id: int) -> dict:
    """Purani photo delete karne ke bajaye alag folder mein rakho."""
    old_dir = f"{settings.SNAPSHOT_DIR}/old/{known_face_id}"
    os.makedirs(old_dir, exist_ok=True)
    path = None
    if oldest.photo_path and os.path.exists(oldest.photo_path):
        path = os.path.join(old_dir, os.path.basename(oldest.photo_path))
        shutil.move(oldest.photo_path, path)
    return {
        "path": path,
        "vector": _vec_to_list(oldest.vector),
        "quality": oldest.quality_score,
        "added_at": oldest.added_at,
        "source_unknown_id": oldest.source_unknown_id,
    }


def _save_old_picture(db: Session, unknown_person_id: int, known_id: int, old: dict):
    """Evicted photo ko actualization row mein save karo (row na ho to banao)."""
    row = db.execute(
        text("SELECT unknown_id FROM unknowns WHERE insight_id = 'unknown-person-' || CAST(:pid AS text) LIMIT 1"),
        {"pid": unknown_person_id},
    ).first()
    if not row:
        return
    now_pkt = datetime.now(PKT).replace(tzinfo=None)
    params = {
        "uid": row[0], "kid": known_id, "pic": old["path"],
        "vec": _vec_to_str(old["vector"]) if old["vector"] else None,
        "q": old["quality"], "at": old["added_at"], "src": old["source_unknown_id"],
        "ts": now_pkt, "kd": now_pkt.date(),
    }
    res = db.execute(text("""
        UPDATE actualization
           SET known_id = :kid, old_picture = :pic, old_embedding = CAST(:vec AS vector),
               old_quality = :q, old_added_at = :at, old_source_unknown_id = :src
         WHERE unkn_id = :uid
    """), params)
    if res.rowcount == 0:
        db.execute(text("""
            INSERT INTO actualization
                (unkn_id, user_code, status, time_stamp, known_date, known_id, old_picture,
                 old_embedding, old_quality, old_added_at, old_source_unknown_id)
            VALUES (:uid, 'admin', 'Successful', :ts, :kd, :kid, :pic,
                    CAST(:vec AS vector), :q, :at, :src)
        """), params)


def _fetch_old_pictures(db: Session, known_id: int, source_unknown_id: int = None) -> list:
    sql = """
        SELECT unkn_id, old_picture, CAST(old_embedding AS text), old_quality,
               old_added_at, old_source_unknown_id
          FROM actualization
         WHERE known_id = :kid AND old_embedding IS NOT NULL
    """
    params = {"kid": known_id}
    if source_unknown_id is not None:
        sql += """ AND unkn_id IN (SELECT unknown_id FROM unknowns
                   WHERE insight_id = 'unknown-person-' || CAST(:src AS text))"""
        params["src"] = source_unknown_id
    sql += " ORDER BY time_stamp DESC"
    rows = db.execute(text(sql), params).fetchall()
    return [
        {"unkn_id": r[0], "path": r[1], "vector": _vec_to_list(r[2]),
         "quality": r[3], "added_at": r[4], "source_unknown_id": r[5]}
        for r in rows
    ]


def _clear_old_picture(db: Session, known_id: int, unkn_id: str):
    db.execute(text("""
        UPDATE actualization
           SET old_picture = NULL, old_embedding = NULL, old_quality = NULL,
               old_added_at = NULL, old_source_unknown_id = NULL
         WHERE known_id = :kid AND unkn_id = :uid
    """), {"kid": known_id, "uid": unkn_id})


def _restore_old_to_known(db: Session, known_face, olds: list):
    known_dir = _known_folder(known_face.name)
    os.makedirs(known_dir, exist_ok=True)
    count = db.query(FaceEmbedding).filter(FaceEmbedding.face_id == known_face.id).count()
    for o in olds:
        if count >= MAX_FACE_IMAGES:
            break
        dst = None
        if o["path"] and os.path.exists(o["path"]):
            dst = os.path.join(known_dir, os.path.basename(o["path"]))
            shutil.move(o["path"], dst)
        db.add(FaceEmbedding(
            face_id=known_face.id,
            vector=o["vector"],
            photo_path=dst,
            quality_score=o["quality"],
            source_unknown_id=o["source_unknown_id"],
            added_at=o["added_at"] or datetime.utcnow(),
        ))
        count += 1
        _clear_old_picture(db, known_face.id, o["unkn_id"])
    db.flush()


def restore_old_pictures_if_room(known_face_id: int, db: Session) -> int:
    """Gallery mein jagah ho aur archived purani photo ho to khud wapas laga do."""
    known_face = db.query(KnownFace).filter(KnownFace.id == known_face_id).first()
    if known_face is None:
        return 0
    count = db.query(FaceEmbedding).filter(FaceEmbedding.face_id == known_face_id).count()
    if count >= MAX_FACE_IMAGES:
        return 0
    olds = _fetch_old_pictures(db, known_face_id)
    if not olds:
        return 0
    _restore_old_to_known(db, known_face, olds)
    db.commit()
    return min(len(olds), MAX_FACE_IMAGES - count)


def crop_face(frame: np.ndarray, bbox, pad: float = 0.25) -> np.ndarray:
    """Face ke gird thora margin rakh kar crop (poora frame nahi)."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = map(int, bbox)
    bw, bh = x2 - x1, y2 - y1
    x1 = max(0, x1 - int(bw * pad)); x2 = min(w, x2 + int(bw * pad))
    y1 = max(0, y1 - int(bh * pad)); y2 = min(h, y2 + int(bh * pad))
    crop = frame[y1:y2, x1:x2].copy()
    return crop if crop.size else frame


def _save_snapshot_into(folder: str, camera_name: str, frame: np.ndarray) -> str:
    os.makedirs(folder, exist_ok=True)
    filename = f"{camera_name}_{int(time.time()*1000)}.webp"
    path = f"{folder}/{filename}"
    success = cv2.imwrite(path, frame, [cv2.IMWRITE_WEBP_QUALITY, 90])
    if not success:
        filename = f"{camera_name}_{int(time.time()*1000)}.jpg"
        path = f"{folder}/{filename}"
        cv2.imwrite(path, frame)
    return path


def resolve_unknown_person(
    embedding: np.ndarray,
    frame: np.ndarray,
    db: Session,
    camera_name: str,
    quality_score: float = None,
    exclude_person_ids: set = None,
    bbox=None,
) -> tuple[UnknownPerson, bool]:
    """
    Matches or creates an UnknownPerson identity.
    Persists sightings with their computed quality_score.
    Ensures representative_snapshot_path always tracks the highest quality snapshot!
    """
    now = datetime.utcnow()
    # Unknown ke liye sirf face crop save hota hai (poora frame nahi)
    face_img = crop_face(frame, bbox) if bbox is not None else frame

    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _DEDUP_LOCK_KEY})

    # exclude_person_ids: isi frame ke doosre logon ki IDs, taake do alag log merge na hon
    pid_a, dist_a = _nearest_by_sighting_embeddings(embedding, db, exclude_person_ids)
    pid_b, dist_b = _nearest_by_reference_embedding(embedding, db, exclude_person_ids)

    best_person_id, best_distance = None, None
    for pid, dist in ((pid_a, dist_a), (pid_b, dist_b)):
        if pid is not None and (best_distance is None or dist < best_distance):
            best_person_id, best_distance = pid, dist

    matched_person = None
    if best_person_id is not None and best_distance <= settings.UNKNOWN_PERSON_DISTANCE_THRESHOLD:
        matched_person = db.query(UnknownPerson).filter(UnknownPerson.id == best_person_id).first()

    if matched_person is not None:
        snapshot_path = _save_snapshot_into(_unknown_folder(matched_person.id), camera_name, face_img)
        current_score = quality_score if quality_score is not None else _score_snapshot(snapshot_path)

        matched_person.last_seen = now
        matched_person.status = "active"

        # Check existing representative snapshot quality
        best_existing_sighting = (
            db.query(UnknownSighting)
            .filter(UnknownSighting.unknown_person_id == matched_person.id)
            .order_by(UnknownSighting.quality_score.desc().nullslast())
            .first()
        )
        prev_best_score = best_existing_sighting.quality_score if best_existing_sighting and best_existing_sighting.quality_score is not None else -1.0

        if current_score >= prev_best_score or not matched_person.representative_snapshot_path:
            matched_person.representative_snapshot_path = snapshot_path

        db.add(
            UnknownSighting(
                unknown_person_id=matched_person.id,
                camera_name=camera_name,
                snapshot_path=snapshot_path,
                quality_score=current_score,
                timestamp=now,
            )
        )
        db.add(
            UnknownEmbedding(
                unknown_person_id=matched_person.id,
                vector=embedding,
                snapshot_path=snapshot_path,
                quality_score=current_score,
                created_at=now,
            )
        )
        db.commit()
        db.refresh(matched_person)
        return matched_person, False

    new_person = UnknownPerson(
        reference_embedding=embedding,
        first_seen=now,
        last_seen=now,
    )
    db.add(new_person)
    db.flush()

    snapshot_path = _save_snapshot_into(_unknown_folder(new_person.id), camera_name, face_img)
    current_score = quality_score if quality_score is not None else _score_snapshot(snapshot_path)
    new_person.representative_snapshot_path = snapshot_path

    db.add(
        UnknownSighting(
            unknown_person_id=new_person.id,
            camera_name=camera_name,
            snapshot_path=snapshot_path,
            quality_score=current_score,
            timestamp=now,
        )
    )
    db.add(
        UnknownEmbedding(
            unknown_person_id=new_person.id,
            vector=embedding,
            snapshot_path=snapshot_path,
            quality_score=current_score,
            created_at=now,
        )
    )
    db.commit()
    db.refresh(new_person)
    return new_person, True


def promote_to_known(unknown_person_id: int, name: str, db: Session) -> KnownFace:
    """
    Converts an unknown_person identity into a registered known_face.
    Selects the single HIGHEST-QUALITY photo for conversion and cover.
    If the known person is already at MAX_FACE_IMAGES, the oldest photo is archived
    (not deleted) and saved into actualization.old_* so it can be restored on revert.
    """
    unknown_person = db.query(UnknownPerson).filter(UnknownPerson.id == unknown_person_id).first()
    if unknown_person is None:
        raise ValueError("unknown_person not found")

    normalized_name = name.strip()

    known_face = (
        db.query(KnownFace)
        .filter(func.lower(KnownFace.name) == normalized_name.lower())
        .first()
    )
    is_new_known_face = known_face is None
    if known_face is None:
        known_face = KnownFace(name=normalized_name)
        db.add(known_face)
        db.flush()

    known_dir = _known_folder(normalized_name)
    os.makedirs(known_dir, exist_ok=True)

    unknown_dir = _unknown_folder(unknown_person.id)
    stored_embeddings = list(unknown_person.embeddings)

    candidates = []
    if os.path.isdir(unknown_dir):
        files = sorted(f for f in os.listdir(unknown_dir) if os.path.isfile(os.path.join(unknown_dir, f)))
        for idx, fname in enumerate(files):
            src = os.path.join(unknown_dir, fname)
            vector = (
                stored_embeddings[idx].vector
                if idx < len(stored_embeddings)
                else unknown_person.reference_embedding
            )
            score = (
                stored_embeddings[idx].quality_score
                if idx < len(stored_embeddings) and stored_embeddings[idx].quality_score is not None
                else _score_snapshot(src)
            )
            candidates.append({
                "src": src,
                "vector": vector,
                "quality": score,
                "mtime": os.path.getmtime(src),
            })
    elif unknown_person.representative_snapshot_path and os.path.exists(
        unknown_person.representative_snapshot_path
    ):
        src = unknown_person.representative_snapshot_path
        candidates.append({
            "src": src,
            "vector": unknown_person.reference_embedding,
            "quality": _score_snapshot(src),
            "mtime": os.path.getmtime(src),
        })

    # Pick the single highest quality photo on file
    if candidates:
        best_candidate = max(candidates, key=lambda c: (c["quality"], c["mtime"]))
        clear_candidates = [best_candidate]
    else:
        clear_candidates = []

    existing_embeddings = (
        db.query(FaceEmbedding)
        .filter(FaceEmbedding.face_id == known_face.id)
        .order_by(FaceEmbedding.added_at.asc())
        .all()
    )

    evicted = None
    moved_count = 0
    new_cover_path = known_face.photo_path
    best_cover_score = -1.0

    # Calculate existing max quality score
    for e in existing_embeddings:
        if e.quality_score is not None and e.quality_score > best_cover_score:
            best_cover_score = e.quality_score

    for candidate in clear_candidates:
        if len(existing_embeddings) >= MAX_FACE_IMAGES:
            oldest = existing_embeddings.pop(0)
            evicted = _archive_old_photo(oldest, known_face.id)
            db.delete(oldest)
            db.flush()

        dst = os.path.join(known_dir, os.path.basename(candidate["src"]))
        shutil.move(candidate["src"], dst)
        new_embedding = FaceEmbedding(
            face_id=known_face.id,
            vector=candidate["vector"],
            photo_path=dst,
            quality_score=candidate["quality"],
            source_unknown_id=unknown_person.id,
            added_at=datetime.utcnow(),
        )
        db.add(new_embedding)
        db.flush()
        existing_embeddings.append(new_embedding)

        if candidate["quality"] >= best_cover_score or not new_cover_path:
            new_cover_path = dst
            best_cover_score = candidate["quality"]
        moved_count += 1

    # Cleanup unselected files in unknown dir
    if os.path.isdir(unknown_dir):
        for fname in os.listdir(unknown_dir):
            fpath = os.path.join(unknown_dir, fname)
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                except OSError:
                    pass
        try:
            os.rmdir(unknown_dir)
        except OSError:
            pass

    if moved_count == 0 and is_new_known_face:
        db.add(FaceEmbedding(
            face_id=known_face.id,
            vector=unknown_person.reference_embedding,
            photo_path=None,
            quality_score=0.0,
            source_unknown_id=unknown_person.id,
            added_at=datetime.utcnow(),
        ))

    if new_cover_path:
        known_face.photo_path = new_cover_path

    # Evicted (purani) photo ko actualization mein save karo, unknown_person delete hone se pehle
    if evicted:
        _save_old_picture(db, unknown_person.id, known_face.id, evicted)

    db.delete(unknown_person)
    db.commit()
    db.refresh(known_face)
    return known_face


def remove_photo_to_unknown(embedding_id: int, db: Session) -> dict:
    """
    Remove/Restore a single known photo back to its original Unknown-NNN identity.
    Also restores the archived old photo (if any) back into the known person's gallery.
    """
    embedding = db.query(FaceEmbedding).filter(FaceEmbedding.id == embedding_id).first()
    if embedding is None:
        raise ValueError(f"FaceEmbedding with id {embedding_id} not found")

    now = datetime.utcnow()
    source_unknown_id = embedding.source_unknown_id
    restored_to_original = False
    target_unknown = None

    # IMPORTANT: naya UnknownPerson insert hone se PEHLE fetch karo,
    # warna DB trigger actualization row saaf kar dega.
    old_pictures = _fetch_old_pictures(db, embedding.face_id)

    if source_unknown_id is not None:
        target_unknown = db.query(UnknownPerson).filter(UnknownPerson.id == source_unknown_id).first()
        if target_unknown is not None:
            restored_to_original = True
        else:
            target_unknown = UnknownPerson(
                id=source_unknown_id,
                reference_embedding=embedding.vector,
                first_seen=embedding.added_at or now,
                last_seen=now,
                status="active",
            )
            db.add(target_unknown)
            db.flush()

            try:
                db.execute(text(
                    "SELECT setval(pg_get_serial_sequence('unknown_persons', 'id'), "
                    "coalesce((SELECT max(id) FROM unknown_persons), 1))"
                ))
            except Exception:
                pass
            restored_to_original = True
    else:
        target_unknown = UnknownPerson(
            reference_embedding=embedding.vector,
            first_seen=embedding.added_at or now,
            last_seen=now,
            status="active",
        )
        db.add(target_unknown)
        db.flush()
        restored_to_original = False

    target_dir = _unknown_folder(target_unknown.id)
    os.makedirs(target_dir, exist_ok=True)

    dst_path = None
    if embedding.photo_path and os.path.exists(embedding.photo_path):
        dst_path = os.path.join(target_dir, os.path.basename(embedding.photo_path))
        shutil.move(embedding.photo_path, dst_path)

    target_unknown.representative_snapshot_path = dst_path or target_unknown.representative_snapshot_path
    target_unknown.last_seen = now
    target_unknown.status = "active"

    db.add(UnknownSighting(
        unknown_person_id=target_unknown.id,
        camera_name="restored-from-known",
        snapshot_path=dst_path,
        quality_score=embedding.quality_score,
        timestamp=now,
    ))
    db.add(UnknownEmbedding(
        unknown_person_id=target_unknown.id,
        vector=embedding.vector,
        snapshot_path=dst_path,
        quality_score=embedding.quality_score,
        created_at=now,
    ))

    face_id = embedding.face_id
    db.delete(embedding)
    db.flush()

    known_face = db.query(KnownFace).filter(KnownFace.id == face_id).first()

    # Purani (evicted) photo wapas known person ki gallery mein
    if known_face and old_pictures:
        _restore_old_to_known(db, known_face, old_pictures)

    if known_face:
        remaining_embeddings = (
            db.query(FaceEmbedding)
            .filter(FaceEmbedding.face_id == face_id)
            .order_by(FaceEmbedding.quality_score.desc().nullslast(), FaceEmbedding.added_at.desc())
            .all()
        )
        if not remaining_embeddings:
            db.execute(
                text("UPDATE events SET known_face_id = NULL WHERE known_face_id = :fid"),
                {"fid": face_id},
            )
            known_dir = _known_folder(known_face.name)
            if os.path.isdir(known_dir):
                shutil.rmtree(known_dir, ignore_errors=True)
            db.delete(known_face)
        else:
            # Auto-update cover to max quality remaining photo
            known_face.photo_path = remaining_embeddings[0].photo_path

    db.commit()
    db.refresh(target_unknown)
    return {
        "id": target_unknown.id,
        "label": f"Unknown-{target_unknown.id:03d}",
        "restored_to_original": restored_to_original,
        "unknown_person": target_unknown,
    }


def revert_to_unknown(known_face_id: int, db: Session) -> UnknownPerson:
    known_face = db.query(KnownFace).filter(KnownFace.id == known_face_id).first()
    if known_face is None:
        raise ValueError("known_face not found")

    now = datetime.utcnow()
    embeddings = list(known_face.embeddings)
    reference_vector = embeddings[0].vector if embeddings else None

    # UnknownPerson insert hone se pehle fetch karo (trigger actualization saaf kar sakta hai)
    old_pictures = _fetch_old_pictures(db, known_face.id)

    source_id = None
    for emb in embeddings:
        if emb.source_unknown_id is not None:
            source_id = emb.source_unknown_id
            break

    new_unknown = None
    if source_id is not None:
        new_unknown = db.query(UnknownPerson).filter(UnknownPerson.id == source_id).first()
        if new_unknown is None:
            new_unknown = UnknownPerson(
                id=source_id,
                reference_embedding=reference_vector,
                first_seen=known_face.created_at or now,
                last_seen=now,
                status="active",
                reverted_from_name=known_face.name,
            )
            db.add(new_unknown)
            db.flush()
            try:
                db.execute(text(
                    "SELECT setval(pg_get_serial_sequence('unknown_persons', 'id'), "
                    "coalesce((SELECT max(id) FROM unknown_persons), 1))"
                ))
            except Exception:
                pass

    if new_unknown is None:
        new_unknown = UnknownPerson(
            reference_embedding=reference_vector,
            first_seen=known_face.created_at or now,
            last_seen=now,
            status="active",
            reverted_from_name=known_face.name,
        )
        db.add(new_unknown)
        db.flush()

    unknown_dir = _unknown_folder(new_unknown.id)
    os.makedirs(unknown_dir, exist_ok=True)

    representative_path = None
    best_score = -1.0
    for emb in embeddings:
        dst_path = None
        if emb.photo_path and os.path.exists(emb.photo_path):
            dst_path = os.path.join(unknown_dir, os.path.basename(emb.photo_path))
            shutil.move(emb.photo_path, dst_path)
            score = emb.quality_score or _score_snapshot(dst_path)
            if score >= best_score:
                best_score = score
                representative_path = dst_path

        db.add(UnknownEmbedding(
            unknown_person_id=new_unknown.id,
            vector=emb.vector,
            snapshot_path=dst_path,
            quality_score=emb.quality_score,
            created_at=emb.added_at or now,
        ))
        db.add(UnknownSighting(
            unknown_person_id=new_unknown.id,
            camera_name="reverted-from-known",
            snapshot_path=dst_path,
            quality_score=emb.quality_score,
            timestamp=emb.added_at or now,
        ))

    # Archived (purani) photos bhi unknown ke saath wapas
    for o in old_pictures:
        dst_path = None
        if o["path"] and os.path.exists(o["path"]):
            dst_path = os.path.join(unknown_dir, os.path.basename(o["path"]))
            shutil.move(o["path"], dst_path)
            score = o["quality"] or _score_snapshot(dst_path)
            if score >= best_score:
                best_score = score
                representative_path = dst_path
        db.add(UnknownEmbedding(
            unknown_person_id=new_unknown.id,
            vector=o["vector"],
            snapshot_path=dst_path,
            quality_score=o["quality"],
            created_at=o["added_at"] or now,
        ))
        db.add(UnknownSighting(
            unknown_person_id=new_unknown.id,
            camera_name="reverted-from-known",
            snapshot_path=dst_path,
            quality_score=o["quality"],
            timestamp=o["added_at"] or now,
        ))
        _clear_old_picture(db, known_face.id, o["unkn_id"])

    if representative_path:
        new_unknown.representative_snapshot_path = representative_path

    db.execute(
        text("UPDATE events SET known_face_id = NULL WHERE known_face_id = :fid"),
        {"fid": known_face_id},
    )

    known_dir = _known_folder(known_face.name)
    if os.path.isdir(known_dir):
        shutil.rmtree(known_dir, ignore_errors=True)

    legacy_dir = f"{settings.SNAPSHOT_DIR}/known/{known_face.name}_{known_face.id}"
    if os.path.isdir(legacy_dir):
        shutil.rmtree(legacy_dir, ignore_errors=True)

    db.delete(known_face)
    db.commit()
    db.refresh(new_unknown)
    return new_unknown


def split_sighting_to_new_unknown(sighting_id: int, db: Session) -> UnknownPerson:
    sighting = db.query(UnknownSighting).filter(UnknownSighting.id == sighting_id).first()
    if sighting is None:
        raise ValueError("sighting not found")

    old_person = db.query(UnknownPerson).filter(UnknownPerson.id == sighting.unknown_person_id).first()
    if old_person is None:
        raise ValueError("parent unknown_person not found")

    matching_embedding = (
        db.query(UnknownEmbedding)
        .filter(
            UnknownEmbedding.unknown_person_id == old_person.id,
            UnknownEmbedding.snapshot_path == sighting.snapshot_path,
        )
        .first()
    )

    now = datetime.utcnow()
    new_person = UnknownPerson(
        reference_embedding=matching_embedding.vector if matching_embedding else old_person.reference_embedding,
        first_seen=sighting.timestamp or now,
        last_seen=sighting.timestamp or now,
        status="active",
    )
    db.add(new_person)
    db.flush()

    new_dir = _unknown_folder(new_person.id)
    os.makedirs(new_dir, exist_ok=True)

    new_snapshot_path = sighting.snapshot_path
    if sighting.snapshot_path and os.path.exists(sighting.snapshot_path):
        new_snapshot_path = os.path.join(new_dir, os.path.basename(sighting.snapshot_path))
        shutil.move(sighting.snapshot_path, new_snapshot_path)

    new_person.representative_snapshot_path = new_snapshot_path

    db.add(UnknownSighting(
        unknown_person_id=new_person.id,
        camera_name=sighting.camera_name,
        snapshot_path=new_snapshot_path,
        quality_score=sighting.quality_score,
        timestamp=sighting.timestamp or now,
    ))
    db.add(UnknownEmbedding(
        unknown_person_id=new_person.id,
        vector=matching_embedding.vector if matching_embedding else old_person.reference_embedding,
        snapshot_path=new_snapshot_path,
        quality_score=matching_embedding.quality_score if matching_embedding else sighting.quality_score,
        created_at=(matching_embedding.created_at if matching_embedding else now) or now,
    ))

    db.delete(sighting)
    if matching_embedding:
        db.delete(matching_embedding)
    db.flush()

    remaining_sightings = (
        db.query(UnknownSighting)
        .filter(UnknownSighting.unknown_person_id == old_person.id)
        .order_by(UnknownSighting.quality_score.desc().nullslast(), UnknownSighting.timestamp.desc())
        .all()
    )
    if not remaining_sightings:
        old_dir = _unknown_folder(old_person.id)
        if os.path.isdir(old_dir):
            try:
                os.rmdir(old_dir)
            except OSError:
                pass
        db.delete(old_person)
    else:
        old_person.representative_snapshot_path = remaining_sightings[0].snapshot_path
        old_person.last_seen = remaining_sightings[0].timestamp

    db.commit()
    db.refresh(new_person)
    return new_person