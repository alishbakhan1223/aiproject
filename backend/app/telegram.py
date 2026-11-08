"""
Sends CCTV security alerts using Telegram Bot API.
"""
import os
import cv2
import requests
import logging
from app.config import settings

logger = logging.getLogger(__name__)


def is_telegram_configured() -> bool:
    """Checks whether Telegram Bot Token and Chat ID are configured."""
    if not settings.TELEGRAM_ENABLED:
        return False
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    chat_id = (settings.TELEGRAM_CHAT_ID or "").strip()

    if not token or not chat_id:
        return False
    if "your_" in token or "your_" in chat_id or "123456" in token:
        return False
    return True


def send_telegram_text(message: str) -> dict:
    """Send text alert via Telegram Bot API."""
    if not is_telegram_configured():
        logger.debug("[Telegram] Skipped: Telegram not configured or disabled.")
        return {"skipped": True, "reason": "Not configured or disabled"}

    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": message,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        res_json = resp.json()
        if not res_json.get("ok"):
            logger.error(f"[Telegram] Error response: {res_json}")
        return res_json
    except Exception as exc:
        logger.error(f"[Telegram] Exception sending text message: {exc}")
        return {"error": str(exc)}


def send_telegram_image_alert(snapshot_path: str, caption: str) -> dict:
    """Send photo snapshot alert with caption via Telegram Bot API."""
    if not is_telegram_configured():
        logger.debug("[Telegram] Skipped: Telegram not configured or disabled.")
        return {"skipped": True, "reason": "Not configured or disabled"}

    token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.TELEGRAM_CHAT_ID

    if not snapshot_path or not os.path.exists(snapshot_path):
        return send_telegram_text(caption)

    try:
        # Convert frame to standard JPEG bytes
        img = cv2.imread(snapshot_path)
        if img is None:
            return send_telegram_text(caption)

        success, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not success:
            return send_telegram_text(caption)
        image_bytes = encoded.tobytes()

        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        files = {
            "photo": ("alert.jpg", image_bytes, "image/jpeg")
        }
        data = {
            "chat_id": chat_id,
            "caption": (caption or "")[:1024],
        }

        resp = requests.post(url, data=data, files=files, timeout=15)
        res_json = resp.json()
        if not res_json.get("ok"):
            logger.error(f"[Telegram] Error sending photo: {res_json}")
            # Fallback to text if photo upload fails
            return send_telegram_text(caption)
        return res_json
    except Exception as exc:
        logger.error(f"[Telegram] Exception sending image alert: {exc}")
        return send_telegram_text(caption)
