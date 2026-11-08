import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.config import settings
from app.whatsapp import send_whatsapp_text, send_whatsapp_image_alert

router = APIRouter(tags=["WhatsApp"])

SNAPSHOT_ROOT = settings.SNAPSHOT_DIR


class WhatsAppMessage(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def not_placeholder_or_empty(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("message cannot be empty")
        if cleaned.lower() == "string":
            raise ValueError(
                "message is still the Swagger default value ('string') — "
                "type a real message before sending"
            )
        return cleaned


@router.post("/send-whatsapp")
def send_whatsapp(payload: WhatsAppMessage):
    result = send_whatsapp_text(payload.message)
    return {"result": result}



class ResendAlert(BaseModel):
    # Either the filename only (e.g. "aziz_1788009108798.webp") if it's
    # directly under SNAPSHOT_ROOT, or "unknown/Unknown-002/aziz_....webp"
    # for a subfolder, or a full absolute path — all three work.
    snapshot: str
    caption: str = "Unknown Person Detected (resent)"

    @field_validator("snapshot")
    @classmethod
    def not_placeholder_or_empty(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned or cleaned.lower() == "string":
            raise ValueError("snapshot filename/path is required")
        return cleaned


@router.post("/resend-alert")
def resend_alert(payload: ResendAlert):
    """
    Resend an existing snapshot as a WhatsApp image alert without having
    to type the full absolute path in Swagger. Accepts either a bare
    filename, a relative path under the snapshots folder, or a full path.
    """
    snapshot_path = payload.snapshot
    if not os.path.isabs(snapshot_path):
        snapshot_path = os.path.join(SNAPSHOT_ROOT, snapshot_path)

    if not os.path.exists(snapshot_path):
        raise HTTPException(
            status_code=404,
            detail=f"Snapshot not found at: {snapshot_path}",
        )

    result = send_whatsapp_image_alert(snapshot_path, payload.caption)
    return {"result": result, "resolved_path": snapshot_path}