import os
import cv2
import shutil
import numpy as np
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, func

from app.database import get_db
from app.models import KnownFace, FaceEmbedding, User
from app.schemas import KnownFaceOut
from app.face_engine import extract_faces, match_face
from app.face_quality import evaluate_face_quality
from app.unknown_person_service import remove_photo_to_unknown, _known_folder, restore_old_pictures_if_room
from app.spec_actualization_service import check_revert_lock_for_photo, check_revert_lock_for_known_face
from app.config import settings
from app.auth import get_current_user

router = APIRouter(tags=["Faces"])
MAX_FACE_IMAGES = 4


@router.post("/register-face", response_model=KnownFaceOut)
async def register_face(
    name: str = Form(...),
    company: str = Form(...),
    branch: str = Form(...),
    role: str = Form(...),
    files: Optional[list[UploadFile]] = File(default=[]),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Register a known person with profile details and real-time duplicate name validation:
    - Requires Full name, Company / Organization, Branch / Location, Role / Designation.
    - Focuses strictly on person's name and details; photos are optional with no mandatory face restriction.
    - Checks database for duplicate name before saving to PostgreSQL:
      Aborts with an error if a person with the exact same name already exists.
    """
    normalized_name = (name or "").strip()
    normalized_company = (company or "").strip()
    normalized_branch = (branch or "").strip()
    normalized_role = (role or "").strip()

    if not normalized_name:
        raise HTTPException(422, "Full name is required")
    if not normalized_company:
        raise HTTPException(422, "Company / Organization is required")
    if not normalized_branch:
        raise HTTPException(422, "Branch / Location is required")
    if not normalized_role:
        raise HTTPException(422, "Role / Designation is required")

    # 1. Validation check: query database to verify if a record with the exact same name already exists
    existing_by_name = (
        db.query(KnownFace)
        .filter(func.lower(func.trim(KnownFace.name)) == normalized_name.lower())
        .first()
    )
    if existing_by_name:
        raise HTTPException(
            status_code=400,
            detail=f"Person already registered in the system (a person named '{existing_by_name.name}' already exists)",
        )

    # 2. Proceed with saving the new record
    known_face = KnownFace(
        name=normalized_name,
        company=normalized_company,
        branch=normalized_branch,
        role=normalized_role,
    )
    db.add(known_face)
    db.flush()

    # 3. Process optional photos if provided (no mandatory image/face restriction checks)
    valid_files = [f for f in (files or []) if f.filename]
    saved_count = 0
    best_quality_score = -1.0
    best_cover_photo_path = None

    if valid_files:
        person_dir = _known_folder(normalized_name)
        os.makedirs(person_dir, exist_ok=True)

        for idx, file in enumerate(valid_files[:4]):
            fname = file.filename.lower() if file.filename else ""
            ctype = (file.content_type or "").lower()
            if not (fname.endswith(".jpg") or fname.endswith(".jpeg") or ctype == "image/jpeg"):
                continue

            try:
                contents = await file.read()
                img_array = np.frombuffer(contents, np.uint8)
                frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if frame is None:
                    continue

                photo_path = f"{person_dir}/{normalized_name}_{idx}_{int(datetime.utcnow().timestamp() * 1000)}.jpg"
                cv2.imwrite(photo_path, frame)

                faces = extract_faces(frame)
                score = 0.0
                vector = None
                if faces:
                    face_obj = faces[0]
                    quality_res = getattr(face_obj, "quality_info", None) or evaluate_face_quality(frame, face_obj)
                    score = quality_res.get("quality_score", 0.0)
                    vector = face_obj.embedding.tolist()

                if score > best_quality_score or best_cover_photo_path is None:
                    best_quality_score = score
                    best_cover_photo_path = photo_path

                if vector is not None:
                    embedding = FaceEmbedding(
                        face_id=known_face.id,
                        vector=vector,
                        photo_path=photo_path,
                        quality_score=score,
                        added_at=datetime.utcnow(),
                    )
                    db.add(embedding)
                    saved_count += 1
            except Exception:
                continue

    if best_cover_photo_path:
        known_face.photo_path = best_cover_photo_path

    db.commit()
    db.refresh(known_face)

    result = KnownFaceOut.model_validate(known_face)
    result.photo_count = saved_count
    return result


@router.get("/known-faces/check-name")
def check_known_face_name(name: str = "", db: Session = Depends(get_db)):
    """
    Real-time check to verify if a known person's name already exists in the database.
    """
    trimmed = (name or "").strip()
    if not trimmed:
        return {"exists": False, "name": ""}
    existing = (
        db.query(KnownFace)
        .filter(func.lower(func.trim(KnownFace.name)) == trimmed.lower())
        .first()
    )
    return {
        "exists": existing is not None,
        "name": existing.name if existing else None,
        "id": existing.id if existing else None,
        "company": existing.company if existing else None,
        "branch": existing.branch if existing else None,
        "role": existing.role if existing else None,
    }


@router.get("/known-faces", response_model=list[KnownFaceOut])
def list_known_faces(db: Session = Depends(get_db)):
    faces = db.query(KnownFace).all()
    out = []
    for f in faces:
        item = KnownFaceOut.model_validate(f)
        item.photo_count = len(f.embeddings)
        is_locked, _, hours_left = check_revert_lock_for_known_face(db, f.id)
        item.revert_locked = is_locked
        item.revert_hours_left = hours_left
        out.append(item)
    return out


@router.delete("/known-faces/{face_id}")
def delete_known_face(
    face_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    known_face = db.query(KnownFace).filter(KnownFace.id == face_id).first()
    if not known_face:
        raise HTTPException(404, "Face not found")
    
    is_locked, locked_photos, _ = check_revert_lock_for_known_face(db, face_id)
    if is_locked:
        raise HTTPException(
            status_code=403,
            detail="Revert window (48 hours) closed. Changes are not allowed anymore.",
        )

    db.execute(
        text("UPDATE events SET known_face_id = NULL WHERE known_face_id = :fid"),
        {"fid": face_id},
    )

    known_dir = _known_folder(known_face.name)
    if os.path.isdir(known_dir):
        shutil.rmtree(known_dir, ignore_errors=True)

    db.delete(known_face)
    db.commit()
    return {"status": "deleted", "id": face_id, "name": known_face.name}


@router.put("/known-faces/{face_id}", response_model=KnownFaceOut)
@router.patch("/known-faces/{face_id}", response_model=KnownFaceOut)
@router.put("/persons/{face_id}", response_model=KnownFaceOut)
@router.patch("/persons/{face_id}", response_model=KnownFaceOut)
async def update_known_face(
    face_id: int,
    name: str = Form(...),
    company: str = Form(...),
    branch: str = Form(...),
    role: str = Form(...),
    keep_photo_ids: Optional[str] = Form(None),
    files: Optional[list[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Updates an existing known person's details:
    - Validates all fields: Full name, Company / Organization, Branch / Location, Role / Designation.
    - Allows keeping, removing, and adding photos while maintaining 1-4 total photos.
    - If photos change, re-runs face embedding generation.
    - If the person's name changes, updates directory on disk and events/alerts records.
    """
    known_face = db.query(KnownFace).filter(KnownFace.id == face_id).first()
    if not known_face:
        raise HTTPException(404, "Face not found")

    trimmed_name = (name or "").strip()
    trimmed_company = (company or "").strip()
    trimmed_branch = (branch or "").strip()
    trimmed_role = (role or "").strip()

    if not trimmed_name:
        raise HTTPException(422, "Full name is required")
    if not trimmed_company:
        raise HTTPException(422, "Company / Organization is required")
    if not trimmed_branch:
        raise HTTPException(422, "Branch / Location is required")
    if not trimmed_role:
        raise HTTPException(422, "Role / Designation is required")

    existing_embeddings = (
        db.query(FaceEmbedding)
        .filter(FaceEmbedding.face_id == face_id)
        .all()
    )

    if keep_photo_ids is not None:
        kept_ids = set()
        cleaned_str = keep_photo_ids.strip()
        if cleaned_str.startswith("["):
            import json
            try:
                kept_ids = set(int(x) for x in json.loads(cleaned_str))
            except Exception:
                pass
        elif cleaned_str:
            for part in cleaned_str.split(","):
                part = part.strip()
                if part.isdigit():
                    kept_ids.add(int(part))
        embeddings_to_keep = [e for e in existing_embeddings if e.id in kept_ids]
        embeddings_to_remove = [e for e in existing_embeddings if e.id not in kept_ids]
    else:
        embeddings_to_keep = list(existing_embeddings)
        embeddings_to_remove = []

    valid_new_files = [f for f in (files or []) if f.filename]
    for f in valid_new_files:
        fname = f.filename.lower() if f.filename else ""
        ctype = (f.content_type or "").lower()
        if not (fname.endswith(".jpg") or fname.endswith(".jpeg") or ctype == "image/jpeg"):
            raise HTTPException(400, f"Only JPG/JPEG photos are supported. Invalid file: {f.filename}")

    total_photos = len(embeddings_to_keep) + len(valid_new_files)
    if total_photos < 1:
        raise HTTPException(400, f"Please keep or upload at least 1 photo (currently {total_photos})")
    if total_photos > 4:
        raise HTTPException(400, f"Maximum 4 photos allowed (currently {total_photos})")

    # Check 48h revert lock on removed embeddings
    for emb in embeddings_to_remove:
        is_locked, hours_left, msg = check_revert_lock_for_photo(db, emb.source_unknown_id)
        if is_locked:
            raise HTTPException(
                403,
                f"Cannot remove photo {emb.id}: Revert window (48 hours) closed.",
            )

    # Perform removal of discarded embeddings
    for emb in embeddings_to_remove:
        if emb.photo_path and os.path.exists(emb.photo_path):
            try:
                os.remove(emb.photo_path)
            except OSError:
                pass
        db.delete(emb)
    db.flush()

    old_name = known_face.name
    photos_changed = len(embeddings_to_remove) > 0 or len(valid_new_files) > 0

    # Handle directory rename and name change
    if trimmed_name != old_name:
        existing_other = (
            db.query(KnownFace)
            .filter(
                func.lower(func.trim(KnownFace.name)) == trimmed_name.lower(),
                KnownFace.id != face_id,
            )
            .first()
        )
        if existing_other:
            raise HTTPException(
                status_code=400,
                detail=f"Person already registered in the system (a person named '{existing_other.name}' already exists)",
            )

        old_dir = _known_folder(old_name)
        new_dir = _known_folder(trimmed_name)
        if os.path.isdir(old_dir):
            if not os.path.exists(new_dir):
                os.rename(old_dir, new_dir)
            else:
                for item in os.listdir(old_dir):
                    src = os.path.join(old_dir, item)
                    dst = os.path.join(new_dir, item)
                    if not os.path.exists(dst):
                        shutil.move(src, dst)
                try:
                    os.rmdir(old_dir)
                except OSError:
                    pass

        # Update path strings in database for kept embeddings
        for emb in embeddings_to_keep:
            if emb.photo_path:
                emb.photo_path = emb.photo_path.replace(f"known/{old_name}", f"known/{trimmed_name}")
                emb.photo_path = emb.photo_path.replace(f"known\\{old_name}", f"known\\{trimmed_name}")

        if known_face.photo_path:
            known_face.photo_path = known_face.photo_path.replace(f"known/{old_name}", f"known/{trimmed_name}")
            known_face.photo_path = known_face.photo_path.replace(f"known\\{old_name}", f"known\\{trimmed_name}")

        # Update person name across events and unknown_persons
        db.execute(
            text("UPDATE events SET person_name = :new_name WHERE known_face_id = :fid"),
            {"new_name": trimmed_name, "fid": face_id},
        )
        db.execute(
            text("UPDATE unknown_persons SET reverted_from_name = :new_name WHERE reverted_from_name = :old_name"),
            {"new_name": trimmed_name, "old_name": old_name},
        )
        known_face.name = trimmed_name

    # Process newly uploaded photos
    person_dir = _known_folder(known_face.name)
    os.makedirs(person_dir, exist_ok=True)

    for idx, file in enumerate(valid_new_files):
        contents = await file.read()
        img_array = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if frame is None:
            db.rollback()
            raise HTTPException(400, f"Could not decode image: {file.filename}")

        faces = extract_faces(frame)
        if not faces:
            db.rollback()
            raise HTTPException(400, f"No clear, acceptable face detected in {file.filename}")

        face_obj = faces[0]
        quality_res = getattr(face_obj, "quality_info", None) or evaluate_face_quality(frame, face_obj)
        score = quality_res.get("quality_score", 0.0)

        matched_name, distance, matched_face_id, _ = match_face(face_obj.embedding, db)
        if matched_name is not None and matched_face_id != face_id:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Person already registered in the system (photo matches registered person '{matched_name}')",
            )

        photo_path = f"{person_dir}/{known_face.name}_{int(datetime.utcnow().timestamp() * 1000)}_{idx}.jpg"
        cv2.imwrite(photo_path, frame)

        new_emb = FaceEmbedding(
            face_id=known_face.id,
            vector=face_obj.embedding.tolist(),
            photo_path=photo_path,
            quality_score=score,
            added_at=datetime.utcnow(),
        )
        db.add(new_emb)
        embeddings_to_keep.append(new_emb)
    db.flush()

    # Re-run embedding generation for existing kept photos if photos changed
    if photos_changed:
        for emb in embeddings_to_keep:
            if emb.photo_path and os.path.exists(emb.photo_path) and emb.id is not None:
                frame = cv2.imread(emb.photo_path)
                if frame is not None:
                    faces = extract_faces(frame)
                    if faces:
                        emb.vector = faces[0].embedding.tolist()
                        q_res = getattr(faces[0], "quality_info", None) or evaluate_face_quality(frame, faces[0])
                        emb.quality_score = q_res.get("quality_score", emb.quality_score or 0.0)

    # Update profile fields
    known_face.company = trimmed_company
    known_face.branch = trimmed_branch
    known_face.role = trimmed_role

    # Set cover photo to the highest quality score embedding
    all_current = (
        db.query(FaceEmbedding)
        .filter(FaceEmbedding.face_id == face_id)
        .order_by(FaceEmbedding.quality_score.desc().nullslast(), FaceEmbedding.added_at.desc())
        .all()
    )
    if all_current:
        known_face.photo_path = all_current[0].photo_path

    db.commit()
    db.refresh(known_face)

    result = KnownFaceOut.model_validate(known_face)
    result.photo_count = len(known_face.embeddings)
    is_locked, _, hours_left = check_revert_lock_for_known_face(db, face_id)
    result.revert_locked = is_locked
    result.revert_hours_left = hours_left
    return result


@router.get("/known-faces/{face_id}/photos")
def list_face_photos(face_id: int, db: Session = Depends(get_db)):
    known_face = db.query(KnownFace).filter(KnownFace.id == face_id).first()
    if not known_face:
        raise HTTPException(404, "Face not found")
    # Archived purani photo ho aur gallery mein jagah ho to khud wapas laga do
    try:
        if restore_old_pictures_if_room(face_id, db):
            db.refresh(known_face)
    except Exception:
        db.rollback()
    photos = sorted(known_face.embeddings, key=lambda e: (e.quality_score or 0.0, e.added_at or datetime.min), reverse=True)
    out = []
    for e in photos:
        is_locked, hours_left, _ = check_revert_lock_for_photo(db, e.source_unknown_id)
        out.append({
            "id": e.id,
            "photo_path": e.photo_path,
            "quality_score": e.quality_score,
            "added_at": e.added_at,
            "source_unknown_id": e.source_unknown_id,
            "is_cover": bool(known_face.photo_path) and e.photo_path == known_face.photo_path,
            "revert_locked": is_locked,
            "revert_hours_left": hours_left,
        })
    return out


@router.post("/known-faces/{face_id}/photos", response_model=KnownFaceOut)
async def add_face_photo(
    face_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Adds one more reference photo to an EXISTING known person.
    If the new photo has a higher quality score than the current cover,
    it automatically becomes the new cover photo."""
    known_face = db.query(KnownFace).filter(KnownFace.id == face_id).first()
    if not known_face:
        raise HTTPException(404, "Face not found")

    contents = await file.read()
    img_array = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(400, "Could not read image")

    faces = extract_faces(frame)
    if not faces:
        raise HTTPException(400, "No clear, acceptable face detected in this photo")

    face_obj = faces[0]
    quality_res = getattr(face_obj, "quality_info", None) or evaluate_face_quality(frame, face_obj)
    new_score = quality_res.get("quality_score", 0.0)

    existing = (
        db.query(FaceEmbedding)
        .filter(FaceEmbedding.face_id == face_id)
        .order_by(FaceEmbedding.added_at.asc())
        .all()
    )
    if len(existing) >= MAX_FACE_IMAGES:
        oldest = existing[0]
        if oldest.photo_path and os.path.exists(oldest.photo_path):
            try:
                os.remove(oldest.photo_path)
            except OSError:
                pass
        db.delete(oldest)
        db.flush()

    known_dir = _known_folder(known_face.name)
    os.makedirs(known_dir, exist_ok=True)
    photo_path = f"{known_dir}/{known_face.name}_{int(datetime.utcnow().timestamp() * 1000)}.jpg"
    cv2.imwrite(photo_path, frame)

    # Determine highest quality score among remaining photos
    best_existing_score = max([e.quality_score or 0.0 for e in existing], default=-1.0)

    db.add(FaceEmbedding(
        face_id=face_id,
        vector=face_obj.embedding.tolist(),
        photo_path=photo_path,
        quality_score=new_score,
        added_at=datetime.utcnow(),
    ))

    if new_score >= best_existing_score or not known_face.photo_path:
        known_face.photo_path = photo_path

    db.commit()
    db.refresh(known_face)

    result = KnownFaceOut.model_validate(known_face)
    result.photo_count = len(known_face.embeddings)
    return result


@router.post("/known-faces/photos/{embedding_id}/remove-to-unknown")
@router.post("/persons/photos/{embedding_id}/remove-to-unknown")
def remove_photo_back_to_unknown(
    embedding_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    embedding = db.query(FaceEmbedding).filter(FaceEmbedding.id == embedding_id).first()
    if not embedding:
        raise HTTPException(status_code=404, detail="Face photo not found")
    is_locked, hours_left, msg = check_revert_lock_for_photo(db, embedding.source_unknown_id)
    if is_locked:
        raise HTTPException(
            status_code=403,
            detail=msg or "Revert window (48 hours) closed. Changes are not allowed anymore.",
        )

    try:
        res = remove_photo_to_unknown(embedding_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Photo wapas unknown ban gayi: us unknown ki purani "Successful" actualization row hata do
    db.execute(
        text("""
            DELETE FROM actualization
            WHERE unkn_id IN (
                SELECT unknown_id FROM unknowns
                WHERE insight_id = 'unknown-person-' || CAST(:pid AS text)
            )
        """),
        {"pid": res["id"]},
    )
    db.commit()

    return {
        "unknown_person_id": res["id"],
        "label": res["label"],
        "restored_to_original": res["restored_to_original"],
    }


@router.delete("/known-faces/{face_id}/photos/{embedding_id}")
def delete_face_photo(
    face_id: int,
    embedding_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    embedding = (
        db.query(FaceEmbedding)
        .filter(FaceEmbedding.id == embedding_id, FaceEmbedding.face_id == face_id)
        .first()
    )
    if not embedding:
        raise HTTPException(404, "Photo not found")

    is_locked, hours_left, msg = check_revert_lock_for_photo(db, embedding.source_unknown_id)
    if is_locked:
        raise HTTPException(
            status_code=403,
            detail=msg or "Revert window (48 hours) closed. Changes are not allowed anymore.",
        )

    known_face = db.query(KnownFace).filter(KnownFace.id == face_id).first()
    was_cover = known_face and known_face.photo_path == embedding.photo_path

    if embedding.photo_path and os.path.exists(embedding.photo_path):
        try:
            os.remove(embedding.photo_path)
        except OSError:
            pass
    db.delete(embedding)
    db.flush()

    if was_cover and known_face:
        # Reassign cover to remaining photo with highest quality score
        remaining = (
            db.query(FaceEmbedding)
            .filter(FaceEmbedding.face_id == face_id)
            .order_by(FaceEmbedding.quality_score.desc().nullslast(), FaceEmbedding.added_at.desc())
            .first()
        )
        known_face.photo_path = remaining.photo_path if remaining else None

    db.commit()
    return {"status": "deleted", "id": embedding_id}


@router.put("/known-faces/{face_id}/cover/{embedding_id}")
def set_cover_photo(
    face_id: int,
    embedding_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    known_face = db.query(KnownFace).filter(KnownFace.id == face_id).first()
    if not known_face:
        raise HTTPException(404, "Face not found")
    embedding = (
        db.query(FaceEmbedding)
        .filter(FaceEmbedding.id == embedding_id, FaceEmbedding.face_id == face_id)
        .first()
    )
    if not embedding:
        raise HTTPException(404, "Photo not found")
    known_face.photo_path = embedding.photo_path
    db.commit()
    return {"status": "ok"}