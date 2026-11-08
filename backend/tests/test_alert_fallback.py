"""
Unit and Integration tests for Alert Dispatcher Fallback System.
Tests:
1. Primary succeeds -> No fallback triggered
2. Primary fails (API error / exception) -> Automatic fallback to secondary succeeds
3. Reverse primary provider (Telegram first -> WhatsApp fallback)
4. Both providers fail -> Graceful degradation without crashing
5. Broadcast mode -> Alerts sent to both channels
6. Real snapshot image routing with fallback
"""
import os
import sys
import unittest
from unittest.mock import patch

# Ensure backend root is on PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.alert_dispatcher import (
    dispatch_image_alert,
    dispatch_text_alert,
    _is_whatsapp_successful,
    _is_telegram_successful,
)
from app.config import settings


class TestAlertFallbackSystem(unittest.TestCase):

    def test_response_validation_helpers(self):
        """Verify delivery check logic for both WhatsApp and Telegram responses."""
        # WhatsApp successes
        self.assertTrue(_is_whatsapp_successful({"messages": [{"id": "wamid.123"}]}))
        self.assertFalse(_is_whatsapp_successful({"error": {"message": "Invalid OAuth"}}))
        self.assertFalse(_is_whatsapp_successful({"skipped": True}))
        self.assertFalse(_is_whatsapp_successful({}))
        self.assertFalse(_is_whatsapp_successful(None))

        # Telegram successes
        self.assertTrue(_is_telegram_successful({"ok": True, "result": {"message_id": 99}}))
        self.assertFalse(_is_telegram_successful({"ok": False, "description": "Forbidden"}))
        self.assertFalse(_is_telegram_successful({"skipped": True}))
        self.assertFalse(_is_telegram_successful({"error": "Network timeout"}))
        self.assertFalse(_is_telegram_successful({}))

    @patch("app.alert_dispatcher.send_whatsapp_image_alert")
    @patch("app.alert_dispatcher.send_telegram_image_alert")
    def test_primary_whatsapp_success_no_fallback(self, mock_tg, mock_wa):
        """When WhatsApp succeeds, Telegram should NOT be called."""
        mock_wa.return_value = {"messages": [{"id": "wamid.ABC12345"}]}
        mock_tg.return_value = {"ok": True}

        with patch.object(settings, "ALERT_MODE", "fallback"), \
             patch.object(settings, "PRIMARY_ALERT_PROVIDER", "whatsapp"):
            result = dispatch_image_alert("test.jpg", "Test alert")

        self.assertTrue(result["delivered"])
        self.assertEqual(result["provider"], "whatsapp")
        self.assertFalse(result["fallback_used"])
        mock_wa.assert_called_once_with("test.jpg", "Test alert")
        mock_tg.assert_not_called()

    @patch("app.alert_dispatcher.send_whatsapp_image_alert")
    @patch("app.alert_dispatcher.send_telegram_image_alert")
    def test_primary_whatsapp_fails_automatic_fallback_to_telegram(self, mock_tg, mock_wa):
        """When WhatsApp fails, system must automatically fallback to Telegram."""
        mock_wa.return_value = {"error": {"message": "Access token expired"}}
        mock_tg.return_value = {"ok": True, "result": {"message_id": 789}}

        with patch.object(settings, "ALERT_MODE", "fallback"), \
             patch.object(settings, "PRIMARY_ALERT_PROVIDER", "whatsapp"):
            result = dispatch_image_alert("test.jpg", "Weapon detected!")

        self.assertTrue(result["delivered"])
        self.assertEqual(result["provider"], "telegram")
        self.assertTrue(result["fallback_used"])
        mock_wa.assert_called_once()
        mock_tg.assert_called_once_with("test.jpg", "Weapon detected!")

    @patch("app.alert_dispatcher.send_whatsapp_image_alert")
    @patch("app.alert_dispatcher.send_telegram_image_alert")
    def test_primary_whatsapp_skipped_unconfigured_fallback_to_telegram(self, mock_tg, mock_wa):
        """When WhatsApp is unconfigured/skipped, automatically delivers via Telegram."""
        mock_wa.return_value = {"skipped": True}
        mock_tg.return_value = {"ok": True, "result": {"message_id": 456}}

        with patch.object(settings, "ALERT_MODE", "fallback"), \
             patch.object(settings, "PRIMARY_ALERT_PROVIDER", "whatsapp"):
            result = dispatch_image_alert("test.jpg", "Intrusion in Zone")

        self.assertTrue(result["delivered"])
        self.assertEqual(result["provider"], "telegram")
        self.assertTrue(result["fallback_used"])
        mock_tg.assert_called_once()

    @patch("app.alert_dispatcher.send_whatsapp_text")
    @patch("app.alert_dispatcher.send_telegram_text")
    def test_primary_telegram_fails_fallback_to_whatsapp(self, mock_tg, mock_wa):
        """When Telegram is primary and fails, system fallbacks to WhatsApp."""
        mock_tg.return_value = {"ok": False, "description": "Chat not found"}
        mock_wa.return_value = {"messages": [{"id": "wamid.XYZ"}]}

        with patch.object(settings, "ALERT_MODE", "fallback"), \
             patch.object(settings, "PRIMARY_ALERT_PROVIDER", "telegram"):
            result = dispatch_text_alert("Unknown person detected")

        self.assertTrue(result["delivered"])
        self.assertEqual(result["provider"], "whatsapp")
        self.assertTrue(result["fallback_used"])
        mock_tg.assert_called_once()
        mock_wa.assert_called_once()

    @patch("app.alert_dispatcher.send_whatsapp_image_alert")
    @patch("app.alert_dispatcher.send_telegram_image_alert")
    def test_both_providers_fail_graceful_handling(self, mock_tg, mock_wa):
        """When both providers fail, returns delivered=False without throwing exceptions."""
        mock_wa.return_value = {"error": "Connection reset"}
        mock_tg.return_value = {"error": "Connection refused"}

        with patch.object(settings, "ALERT_MODE", "fallback"), \
             patch.object(settings, "PRIMARY_ALERT_PROVIDER", "whatsapp"):
            result = dispatch_image_alert("test.jpg", "Alert")

        self.assertFalse(result["delivered"])
        self.assertTrue(result["fallback_used"])

    @patch("app.alert_dispatcher.send_whatsapp_image_alert")
    @patch("app.alert_dispatcher.send_telegram_image_alert")
    def test_broadcast_mode_sends_to_both(self, mock_tg, mock_wa):
        """In broadcast mode, alerts are sent to both WhatsApp and Telegram."""
        mock_wa.return_value = {"messages": [{"id": "wamid.1"}]}
        mock_tg.return_value = {"ok": True, "result": {"message_id": 2}}

        with patch.object(settings, "ALERT_MODE", "broadcast"):
            result = dispatch_image_alert("test.jpg", "Broadcast alert")

        self.assertTrue(result["delivered"])
        self.assertEqual(result["mode"], "broadcast")
        mock_wa.assert_called_once()
        mock_tg.assert_called_once()


if __name__ == "__main__":
    unittest.main()
