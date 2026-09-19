"""Повторная доставка входящего не должна ломать транзакцию.

Дедупликация ставит запись в inbox и ловит IntegrityError на повторе. Ловить
его без точки сохранения нельзя: Postgres обрывает транзакцию целиком, и
следующий же запрос падает с TransactionManagementError. А вызывают это
изнутри транзакции — воркер держит ``tenant_atomic`` на весь цикл поллинга,
так что первый повтор ронял не дедупликацию, а весь цикл организации.
"""

from __future__ import annotations

from django.db import transaction
from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.ingest import _already_processed, ingest_inbound
from chatballs.conversations.models import Message
from chatballs.conversations.transports.base import InboundMessage
from chatballs.events.models import InboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import system_tenant_context


class InboundDeduplicationTests(TestCase):
    def setUp(self) -> None:
        result = bootstrap_owner(email="ingest-owner@example.com", password="Owner-Password-2026!")
        self.context = system_tenant_context(result.organization)

    def test_repeat_is_reported_without_breaking_the_transaction(self) -> None:
        with tenant_atomic(self.context):
            first = _already_processed(self.context, "telegram:1", "update-42", "привет")
            second = _already_processed(self.context, "telegram:1", "update-42", "привет")

            self.assertFalse(first)
            self.assertTrue(second)

            # Главное: транзакция жива и дальше в ней можно работать. Раньше
            # именно здесь всё и разваливалось.
            self.assertEqual(
                InboxEvent.objects.filter(external_event_id="update-42").count(), 1
            )

    def test_repeat_does_not_roll_back_work_done_earlier(self) -> None:
        with transaction.atomic():
            with tenant_atomic(self.context):
                _already_processed(self.context, "max:7", "update-1", "первое")
                _already_processed(self.context, "max:7", "update-1", "первое")
                _already_processed(self.context, "max:7", "update-2", "второе")

        self.assertEqual(InboxEvent.objects.filter(source="max:7").count(), 2)

    def test_different_sources_do_not_collide(self) -> None:
        with tenant_atomic(self.context):
            self.assertFalse(_already_processed(self.context, "telegram:1", "shared-id", "текст"))
            self.assertFalse(_already_processed(self.context, "max:2", "shared-id", "текст"))


class InboundMessageIdentityTests(TestCase):
    def setUp(self) -> None:
        result = bootstrap_owner(email="inbound-identity@example.com", password="Owner-Password-2026!")
        self.organization = result.organization
        self.context = system_tenant_context(self.organization)
        self.channel = Channel.objects.create(
            organization=self.organization,
            code="identity-tests",
            name="Identity tests",
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.TELEGRAM,
            name="Identity test connection",
            channel=self.channel,
        )

    def test_legacy_inbound_uses_message_id_as_event_id(self) -> None:
        inbound = InboundMessage(
            external_id="message-legacy",
            user_id="user-1",
            chat_id="chat-1",
            text="legacy",
            display_name="Guest",
        )

        with tenant_atomic(self.context):
            ingest_inbound(self.integration, inbound)

        self.assertEqual(
            InboxEvent.objects.get(source=f"telegram:{self.integration.id}").external_event_id,
            "message-legacy",
        )
        self.assertEqual(Message.objects.get(external_id="message-legacy").external_id, "message-legacy")

    def test_separate_event_id_is_used_only_for_inbox_event(self) -> None:
        inbound = InboundMessage(
            external_id="provider-message-1",
            external_event_id="gateway-event-1",
            user_id="user-1",
            chat_id="chat-1",
            text="separate identities",
            display_name="Guest",
        )

        with tenant_atomic(self.context):
            ingest_inbound(self.integration, inbound)

        event = InboxEvent.objects.get(source=f"telegram:{self.integration.id}")
        message = Message.objects.get(external_id="provider-message-1")
        self.assertEqual(event.external_event_id, "gateway-event-1")
        self.assertEqual(message.external_id, "provider-message-1")
        self.assertNotEqual(event.external_event_id, message.external_id)
