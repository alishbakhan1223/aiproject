import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.config import settings
from app.telegram import send_telegram_text, send_telegram_image_alert, is_telegram_configured

router = APIRouter(tags=["Telegram"])

SNAPSHOT_ROOT = settings.SNAPSHOT_DIR


class TelegramMessage(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def not_placeholder_or_empty(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("message cannot be empty")
        if cleaned.lower() == "string":
            raise ValueError("message is still default 'string' — type a real message")
        return cleaned


class TelegramResendAlert(BaseModel):
    snapshot: str
    caption: str = "🚨 CCTV Alert (Test / Resent)"

    @field_validator("snapshot")
    @classmethod
    def not_placeholder_or_empty(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned or cleaned.lower() == "string":
            raise ValueError("snapshot filename/path is required")
        return cleaned


@router.get("/telegram/status")
def get_telegram_status():
    """Check if Telegram alerting is enabled and configured."""
    return {
        "enabled": settings.TELEGRAM_ENABLED,
        "configured": is_telegram_configured(),
        "chat_id_set": bool(settings.TELEGRAM_CHAT_ID),
        "bot_token_set": bool(settings.TELEGRAM_BOT_TOKEN),
    }


@router.post("/send-telegram")
def send_telegram(payload: TelegramMessage):
    """Send text test message via Telegram bot."""
    result = send_telegram_text(payload.message)
    return {"result": result}


@router.post("/resend-telegram-alert")
def resend_telegram_alert(payload: TelegramResendAlert):
    """Send a snapshot photo with caption via Telegram bot."""
    snapshot_path = payload.snapshot
    if not os.path.isabs(snapshot_path):
        snapshot_path = os.path.join(SNAPSHOT_ROOT, snapshot_path)

    if not os.path.exists(snapshot_path):
        raise HTTPException(
            status_code=404,
            detail=f"Snapshot not found at: {snapshot_path}",
        )

    result = send_telegram_image_alert(snapshot_path, payload.caption)
    return {"result": result, "resolved_path": snapshot_path}
