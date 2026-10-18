"""Сбой опроса подключения: пауза с удвоением и тишина в журнале.

Раньше подключение с ненастоящим токеном писало предупреждение каждые три
секунды. Теперь после сбоя оно пропускается с растущей паузой, журнал видит
первый сбой, выход на максимальную паузу и восстановление, а курсор при
сбое не двигается. Демо-подключения не опрашиваются вовсе.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations import poller
from chatballs.conversations.transports.base import InboundMessage
from chatballs.native_mirror.vk_adapter import VkNativeReply
from chatballs.conversations.transports import backoff, poll
from chatballs.conversations.transports.errors import PollFailed
from chatballs.identity.models import Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


class PollBackoffTests(TestCase):
    def setUp(self) -> None:
        backoff.reset()
        self.addCleanup(backoff.reset)
        self.organization = Organization.objects.create(name="Poll", slug="poll-org")
        with tenant_atomic(self.organization.id):
            self.channel = Channel.objects.create(organization=self.organization, name="Main", code="main")
            self.integration = Integration.objects.create(
                organization=self.organization,
                kind=IntegrationKind.MESSENGER,
                provider=IntegrationProvider.TELEGRAM,
                name="Bot",
                secret="0000:not-a-token",
                channel=self.channel,
                poll_marker="41",
            )

    def _fail(self, *_args, **_kwargs):
        raise PollFailed("HTTP Error 401: Unauthorized")

    def test_failure_is_logged_once_and_then_skipped(self) -> None:
        with mock.patch.dict(poller.transports._POLL, {IntegrationProvider.TELEGRAM: self._fail}):
            with self.assertLogs("chatballs.conversations.transports.backoff", level="WARNING") as logs:
                self.assertEqual(poll(self.integration), ([], "41"))
            self.assertEqual(len(logs.output), 1)
            self.assertIn("401", logs.output[0])
            # Пока пауза не вышла, транспорт не вызывается и журнал молчит.
            with mock.patch.object(backoff, "_now", return_value=backoff._now()):
                with self.assertNoLogs("chatballs.conversations.transports.backoff", level="WARNING"):
                    self.assertEqual(poll(self.integration), ([], "41"))
            self.assertTrue(backoff.should_skip(self.integration.id))

    def test_delay_doubles_up_to_the_cap_and_recovery_is_logged(self) -> None:
        clock = [1000.0]
        with mock.patch.object(backoff, "_now", side_effect=lambda: clock[0]):
            with mock.patch.dict(poller.transports._POLL, {IntegrationProvider.TELEGRAM: self._fail}):
                delays = []
                for _ in range(10):
                    poll(self.integration)
                    state = backoff._failures[self.integration.id]
                    delays.append(state.delay)
                    clock[0] = state.next_attempt_at  # ждём ровно до следующей попытки
            self.assertEqual(delays[:3], [6.0, 12.0, 24.0])
            self.assertEqual(delays[-1], backoff.MAX_DELAY_SECONDS)
            self.assertTrue(all(delay <= backoff.MAX_DELAY_SECONDS for delay in delays))

            with mock.patch.dict(poller.transports._POLL, {IntegrationProvider.TELEGRAM: lambda _i: ([], "42")}):
                with self.assertLogs("chatballs.conversations.transports.backoff", level="INFO") as logs:
                    self.assertEqual(poll(self.integration), ([], "42"))
            self.assertIn("recovered", logs.output[0])
            self.assertNotIn(self.integration.id, backoff._failures)

    def test_demo_seed_connections_are_not_polled(self) -> None:
        with tenant_atomic(self.organization.id):
            Integration.objects.filter(pk=self.integration.pk).update(config={"demoSeed": True})
            context = TenantContext.for_resource(self.organization)
            with mock.patch("chatballs.conversations.poller.transports.poll") as polled:
                poller.poll_all_messengers(context)
        polled.assert_not_called()

    def _configure_vk(self, mode="SHADOW") -> None:
        self.integration.provider = IntegrationProvider.VK
        self.integration.config = {"bot_id": "42", "native_mirror_mode": mode}
        self.integration.save(update_fields=["provider", "config"])

    def test_vk_failure_in_client_ingest_keeps_cursor_for_redelivery(self) -> None:
        with tenant_atomic(self.organization.id):
            self._configure_vk()
            context = TenantContext.for_resource(self.organization)
            incoming = InboundMessage(
                external_id="500", user_id="77", chat_id="77",
                text="Question", display_name="",
            )
            batch = ([incoming, VkNativeReply("77", "600", "Answer")], "42")
            with mock.patch.object(poller.transports, "poll", return_value=batch), \
                    mock.patch.object(poller, "_ingest_polled", side_effect=RuntimeError("temporary")):
                with self.assertLogs("chatballs.conversations.poller", level="ERROR"):
                    poller.poll_all_messengers(context)
            self.integration.refresh_from_db()
            self.assertEqual(self.integration.poll_marker, "41")

            with mock.patch.object(poller.transports, "poll", return_value=batch), \
                    mock.patch.object(poller, "_ingest_polled", return_value=True) as ingested:
                self.assertEqual(poller.poll_all_messengers(context), 1)
            ingested.assert_called_once_with(self.integration, incoming)
            self.integration.refresh_from_db()
            self.assertEqual(self.integration.poll_marker, "42")

    def test_vk_enabled_before_mirror_persistence_keeps_cursor(self) -> None:
        with tenant_atomic(self.organization.id):
            self._configure_vk(mode="ENABLED")
            context = TenantContext.for_resource(self.organization)
            batch = ([VkNativeReply("77", "600", "Answer")], "42")
            with mock.patch.object(poller.transports, "poll", return_value=batch):
                with self.assertLogs("chatballs.conversations.poller", level="ERROR"):
                    self.assertEqual(poller.poll_all_messengers(context), 0)
            self.integration.refresh_from_db()
            self.assertEqual(self.integration.poll_marker, "41")

            self.integration.config = {"bot_id": "42", "native_mirror_mode": "SHADOW"}
            self.integration.save(update_fields=["config"])
            with mock.patch.object(poller.transports, "poll", return_value=batch):
                self.assertEqual(poller.poll_all_messengers(context), 0)
            self.integration.refresh_from_db()
            self.assertEqual(self.integration.poll_marker, "42")

    def test_non_vk_legacy_ingest_failure_keeps_existing_marker_policy(self) -> None:
        with tenant_atomic(self.organization.id):
            context = TenantContext.for_resource(self.organization)
            incoming = InboundMessage(
                external_id="500", user_id="77", chat_id="77",
                text="Question", display_name="",
            )
            with mock.patch.object(
                poller.transports, "poll", return_value=([incoming], "42")
            ), mock.patch.object(poller, "_ingest_polled", side_effect=RuntimeError("old path")):
                with self.assertLogs("chatballs.conversations.poller", level="ERROR"):
                    poller.poll_all_messengers(context)
            self.integration.refresh_from_db()
            # B is a VK-only fix; no surprise change in upstream TG/MAX/EMAIL.
            self.assertEqual(self.integration.poll_marker, "42")
