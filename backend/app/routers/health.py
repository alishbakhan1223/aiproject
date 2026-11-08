from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import SessionLocal
from app.redis_stream import _client as redis_client
from app.camera_worker import get_all_worker_status
from app.schemas import HealthOut, WorkerHealth, SystemResources

import psutil

router = APIRouter(tags=["Health"])


def _get_system_resources() -> SystemResources:
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent

    gpu_percent = None
    gpu_mem_percent = None
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        gpu_percent = float(util.gpu)
        gpu_mem_percent = round(mem.used / mem.total * 100, 1)
    except Exception:
        pass  # pynvml not installed or no GPU — returns null

    return SystemResources(
        cpu_percent=cpu,
        ram_percent=ram,
        gpu_percent=gpu_percent,
        gpu_memory_percent=gpu_mem_percent,
    )


@router.get("/health")
def health():
    db_ok = True
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_ok = False

    redis_ok = True
    try:
        redis_client.ping()
    except Exception:
        redis_ok = False

    raw_workers = get_all_worker_status()
    workers = []
    for w in raw_workers:
        workers.append(WorkerHealth(
            camera_id=w.get("camera_id"),
            camera_name=w.get("camera_name"),
            running=w.get("running", False),
            state=w.get("state"),
            last_frame_at=w.get("last_frame_at"),
            frames_processed=w.get("frames_processed", 0),
            reconnect_count=w.get("reconnect_count", 0),
            fps_source=w.get("fps_source"),
            capture_fps=w.get("capture_fps"),
            frame_age_ms=w.get("frame_age_ms"),
            dropped_frames=w.get("dropped_frames", 0),
            frames_delivered=w.get("frames_delivered", 0),
            stream_errors=w.get("stream_errors", 0),
            jpeg_encode_ms=w.get("jpeg_encode_ms"),
            yolo_fps=w.get("yolo_fps"),
            yolo_inference_ms=w.get("yolo_inference_ms"),
            insightface_inference_ms=w.get("insightface_inference_ms"),
            detection_frame_age_ms=w.get("detection_frame_age_ms"),
            detection_frames_skipped=w.get("detection_frames_skipped", 0),
            latest_detection_at=w.get("latest_detection_at"),
        ))

    return JSONResponse(content=HealthOut(
        api_status="running",
        redis_connected=redis_ok,
        database_connected=db_ok,
        workers=workers,
        system=_get_system_resources(),
    ).model_dump())
