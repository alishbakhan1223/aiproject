from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Union


class UserOut(BaseModel):
    """User data returned to frontend (no password)"""
    id: int
    username: str
    email: Optional[str] = None
    role: str  # admin | user
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login: Optional[datetime] = None

    class Config:
        from_attributes = True


class EventOut(BaseModel):
    id: int
    event_type: str
    camera_name: str
    timestamp: datetime
    snapshot_path: Optional[str] = None
    person_name: Optional[str] = None
    is_unknown: bool
    object_name: Optional[str] = None
    confidence: Optional[float] = None
    in_zone: Optional[bool] = None
    known_face_id: Optional[int] = None
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KnownFaceOut(BaseModel):
    id: int
    name: str
    photo_path: Optional[str] = None
    company: Optional[str] = None
    branch: Optional[str] = None
    role: Optional[str] = None
    created_at: datetime
    photo_count: int = 0
    revert_locked: bool = False
    revert_hours_left: Optional[float] = None

    class Config:
        from_attributes = True


class ConfirmKnownIn(BaseModel):
    """Body for POST /events/{event_id}/confirm-known"""
    known_face_id: int


class UnknownPersonOut(BaseModel):
    id: int
    representative_snapshot_path: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    detection_count: int = 0
    status: str = "active"
    reverted_from_name: Optional[str] = None
    mapping_days_left: Optional[int] = None

    class Config:
        from_attributes = True


class UnknownSightingOut(BaseModel):
    id: int
    unknown_person_id: int
    camera_name: str
    snapshot_path: Optional[str] = None
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True


class CameraCreate(BaseModel):
    name: str
    source: str


class CameraOut(BaseModel):
    id: int
    name: str
    source: str
    is_active: bool

    class Config:
        from_attributes = True


class StatisticsOut(BaseModel):
    total_events: int
    unknown_person_events: int
    restricted_object_events: int
    weapon_events: int = 0
    known_person_events: int
    forensic_confirmations: int
    total_known_faces: int
    active_cameras: int


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    username: str  # kept for backward compatibility
    role: str


class ZoneIn(BaseModel):
    camera_id: int
    points: list[list[float]]  # [[x,y], [x,y], ...] in source-frame pixel coords


class ZoneOut(BaseModel):
    camera_id: int
    points: list[list[float]]


class WorkerHealth(BaseModel):
    # Availability
    camera_id: int
    camera_name: str
    running: bool
    state: Optional[str] = None
    last_frame_at: Optional[str] = None
    frames_processed: int = 0
    reconnect_count: int = 0

    # Capture pipeline
    fps_source: Optional[Union[float, str]] = None
    capture_fps: Optional[float] = None
    frame_age_ms: Optional[float] = None
    dropped_frames: int = 0

    # Stream pipeline
    frames_delivered: int = 0
    stream_errors: int = 0
    jpeg_encode_ms: Optional[float] = None

    # AI pipeline
    yolo_fps: Optional[float] = None
    yolo_inference_ms: Optional[float] = None
    insightface_inference_ms: Optional[float] = None
    detection_frame_age_ms: Optional[float] = None
    detection_frames_skipped: int = 0
    latest_detection_at: Optional[str] = None


class SystemResources(BaseModel):
    cpu_percent: Optional[float] = None
    ram_percent: Optional[float] = None
    gpu_percent: Optional[float] = None
    gpu_memory_percent: Optional[float] = None


class HealthOut(BaseModel):
    api_status: str
    redis_connected: bool
    database_connected: bool
    workers: list[WorkerHealth]
    system: Optional[SystemResources] = None