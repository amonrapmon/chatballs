"""VK Native Mirror toggle: safe config round-trip without changing other transports."""

from datetime import UTC, datetime

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.integrations.serializers import integration_payload
from chatballs.integrations.services import _normalized_config


class VkNativeMirrorSettingsTests(SimpleTestCase):
    def test_default_is_legacy_and_serializes_as_off(self):
        config = _normalized_config(IntegrationProvider.VK, {"baseUrl": "https://api.vk.com/method"})
        self.assertNotIn("native_mirror_mode", config)
        integration = Integration(
            provider=IntegrationProvider.VK, name="VK", config=config,
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        self.assertFalse(integration_payload(integration)["config"]["nativeMirrorEnabled"])

    def test_explicit_toggle_round_trip(self):
        for enabled, expected in ((True, "ENABLED"), (False, "DISABLED")):
            with self.subTest(enabled=enabled):
                config = _normalized_config(
                    IntegrationProvider.VK, {"nativeMirrorEnabled": enabled}
                )
                self.assertEqual(config["native_mirror_mode"], expected)
                integration = Integration(
                    provider=IntegrationProvider.VK, name="VK", config=config,
                    created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
                )
                self.assertIs(integration_payload(integration)["config"]["nativeMirrorEnabled"], enabled)

    def test_unrelated_edit_preserves_existing_mode_and_verified_identity(self):
        prior = {
            "native_mirror_mode": "SHADOW",
            "bot_id": "42",
            "bot_username": "test_community",
            "bot_name": "Test community",
        }
        unchanged = _normalized_config(IntegrationProvider.VK, {"proxyUrl": ""}, prior)
        self.assertEqual(unchanged["native_mirror_mode"], "SHADOW")
        self.assertEqual(unchanged["bot_id"], "42")
        self.assertEqual(unchanged["bot_username"], "test_community")
        self.assertEqual(unchanged["bot_name"], "Test community")
        enabled = _normalized_config(
            IntegrationProvider.VK, {"nativeMirrorEnabled": True}, prior
        )
        self.assertEqual(enabled["native_mirror_mode"], "ENABLED")
        self.assertEqual(enabled["bot_id"], "42")

    def test_rejects_non_boolean_toggle(self):
        for bad in ("true", 1, None, []):
            with self.subTest(value=bad):
                with self.assertRaises(ValidationError):
                    _normalized_config(IntegrationProvider.VK, {"nativeMirrorEnabled": bad})

    def test_other_transports_ignore_vk_setting(self):
        config = _normalized_config(
            IntegrationProvider.TELEGRAM, {"nativeMirrorEnabled": True}
        )
        self.assertNotIn("native_mirror_mode", config)
