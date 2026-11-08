from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Camera, User
from app.schemas import CameraCreate, CameraOut
from app.camera_worker import start_camera, stop_camera
from app.auth import get_current_user

router = APIRouter(prefix="/camera", tags=["Camera"])


@router.post("/add", response_model=CameraOut)
def add_camera(payload: CameraCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    camera = Camera(name=payload.name, source=payload.source)
    db.add(camera)
    db.commit()
    db.refresh(camera)
    return camera


@router.get("/list", response_model=list[CameraOut])
def list_cameras(db: Session = Depends(get_db)):
    return db.query(Camera).all()


@router.post("/start")
def start(camera_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(404, "Camera not found")
    start_camera(camera.id, camera.name, camera.source)
    camera.is_active = True
    db.commit()
    return {"status": "started", "camera": camera.name}


@router.post("/stop")
def stop(camera_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(404, "Camera not found")
    stop_camera(camera.id)
    camera.is_active = False
    db.commit()
    return {"status": "stopped", "camera": camera.name}
