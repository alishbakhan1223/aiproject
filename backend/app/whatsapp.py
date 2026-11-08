"""
Sends WhatsApp alerts using Meta Cloud API.
"""
import cv2
import os
import requests
from app.config import settings


def _is_meta_configured() -> bool:
    token = (settings.WHATSAPP_TOKEN or "").strip()
    phone_id = (settings.WHATSAPP_PHONE_NUMBER_ID or "").strip()
    admin_num = (settings.WHATSAPP_ADMIN_NUMBER or "").strip()

    if not token or not phone_id or not admin_num:
        return False
    if "your_" in token.lower() or "your_" in phone_id.lower() or "91xxxx" in admin_num or "xxxxxxxx" in phone_id:
        return False
    return True


def _send_meta_text(message: str) -> dict:
    token = settings.WHATSAPP_TOKEN
    phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    admin_num = settings.WHATSAPP_ADMIN_NUMBER

    url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": admin_num,
        "type": "text",
        "text": {"body": message},
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        return resp.json()
    except Exception as exc:
        print(f"[meta_whatsapp] Exception sending text message: {exc}")
        return {"error": str(exc)}


def send_whatsapp_text(message: str) -> dict:
    """Send text alert via Meta WhatsApp Cloud API."""
    if _is_meta_configured():
        return _send_meta_text(message)
    return {"skipped": True, "reason": "Meta WhatsApp not configured"}


def send_whatsapp_image_alert(snapshot_path: str, caption: str) -> dict:
    if _is_meta_configured():
        if not snapshot_path or not os.path.exists(snapshot_path):
            return _send_meta_text(caption)
        try:
            # Convert to JPEG in-memory regardless of source format (webp/jpg/png)
            # so the content-type we send always matches the actual bytes.
            img = cv2.imread(snapshot_path)
            if img is None:
                return _send_meta_text(caption)
            success, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not success:
                return _send_meta_text(caption)
            image_bytes = encoded.tobytes()

            upload_url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/media"
            headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}
            files = {"file": ("alert.jpg", image_bytes, "image/jpeg")}
            data = {"messaging_product": "whatsapp", "type": "image/jpeg"}
            upload_resp = requests.post(upload_url, headers=headers, data=data, files=files, timeout=15)
            upload_json = upload_resp.json()
            media_id = upload_json.get("id")
            if not media_id:
                return _send_meta_text(caption)

            send_url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": settings.WHATSAPP_ADMIN_NUMBER,
                "type": "image",
                "image": {"id": media_id, "caption": caption[:1024]},
            }
            send_resp = requests.post(send_url, headers={**headers, "Content-Type": "application/json"}, json=payload, timeout=10)
            return send_resp.json()
        except Exception as exc:
            print(f"[meta_whatsapp] Exception sending image alert: {exc}")
            return _send_meta_text(caption)

    return {"skipped": True, "reason": "Meta WhatsApp not configured"}


# --- Alert Message Formatters ---

def build_unknown_person_message(camera_name, timestamp, confidence):
    return (
        "🚨 Unknown Person Detected\n"
        f"Camera: {camera_name}\n"
        f"Time: {timestamp}\n"
        f"Confidence: {confidence:.0%}\n"
        "Status: Face not found in registered members."
    )


def build_restricted_object_message(camera_name, object_name, timestamp, confidence):
    return (
        "🚨 Restricted Object Detected\n"
        f"Camera: {camera_name}\n"
        f"Object: {object_name}\n"
        f"Time: {timestamp}\n"
        f"Confidence: {confidence:.0%}"
    )


def build_weapon_message(camera_name, weapon_class, timestamp, confidence, zone_name=None, forensic_confirmed=True):
    zone_str = f"\nZone: {zone_name}" if zone_name else ""
    verif_str = "Confirmed" if forensic_confirmed else "Primary Alert"
    return (
        "⚠️ Weapon Detected\n"
        f"Camera: {camera_name}\n"
        f"Type: {weapon_class.capitalize()}\n"
        f"Confidence: {confidence:.0%}"
        f"{zone_str}\n"
        f"Time: {timestamp}\n"
        f"Verification: {verif_str}"
    )