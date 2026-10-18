"""Stage A/B: VK mirror observation must not persist or invent authors."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from chatballs.native_mirror.vk_adapter import VkNativeReply, observe_vk_reply


class VkMirrorShadowTests(SimpleTestCase):
    def test_shadow_logs_only_metadata(self) -> None:
        integration = SimpleNamespace(id=12, config={"native_mirror_mode": "SHADOW"})
        event = VkNativeReply(peer_id="87", message_id="7", text="PRIVATE ANSWER")
        with self.assertLogs("chatballs.native_mirror.vk_adapter", level="INFO") as logs:
            observe_vk_reply(integration, event)
        self.assertIn("has_peer=True", logs.output[0])
        self.assertIn("has_id=True", logs.output[0])
        self.assertNotIn("PRIVATE ANSWER", logs.output[0])
        self.assertNotIn("peer_id=87", logs.output[0])

    def test_disabled_and_legacy_have_no_mirror_side_effects(self) -> None:
        event = VkNativeReply(peer_id="87", message_id="7", text="Ignored")
        for config in ({}, {"native_mirror_mode": "DISABLED"}):
            with self.subTest(config=config):
                observe_vk_reply(SimpleNamespace(id=12, config=config), event)

    def test_enabled_requires_tenant_context(self) -> None:
        integration = SimpleNamespace(id=12, config={"native_mirror_mode": "ENABLED"})
        with self.assertRaisesRegex(RuntimeError, "tenant context"):
            observe_vk_reply(integration, VkNativeReply("87", "7", "Text"))
