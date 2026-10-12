"""Reusable PostgreSQL fixture for Native Mirror vs AI-turn races."""

from datetime import UTC, datetime

from chatballs.ai.models import AIAgent, AIAgentStatus
from chatballs.channels.models import Channel
from chatballs.conversations.ai_turn import AI_TURN_REQUESTED, _begin
from chatballs.conversations.ai_turn_completion import _commit_if_current
from chatballs.conversations.ai_turn_result import store_answer
from chatballs.conversations.gateway_delivery import GATEWAY_DELIVERY_COMMAND_REQUESTED
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import ControlMode, Message, MessageAuthor, SystemEvent
from chatballs.conversations.transports.base import InboundMessage
from chatballs.events.models import OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.native_mirror.classification import OriginClass
from chatballs.native_mirror.contracts import NativeReplyEvent
from chatballs.native_mirror.service import accept_native_reply
from chatballs.testing import system_tenant_context
from chatballs.tenancy.database import tenant_atomic


class NativeMirrorTurnFixture:
    def setUp(self):
        result = bootstrap_owner(
            email="mirror-supersede@example.com", password="temporary-password"
        )
        self.organization = result.organization
        self.owner = result.owner
        self.context = system_tenant_context(self.organization)
        self.channel = Channel.objects.create(
            organization=self.organization, code="mirror-supersede", name="Mirror AI"
        )
        self.agent = AIAgent.objects.create(
            channel=self.channel, name="AI", model="openai/gpt-4o-mini",
            status=AIAgentStatus.ACTIVE,
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.GATEWAY,
            channel=self.channel, name="Test Gateway", secret="test",
            config={
                "source_id": "tg-native", "base_url": "https://gateway.example.test/",
                "native_mirror_mode": "ENABLED",
            },
        )
        self._inbound("client-1")
        self.message = Message.objects.get(
            author_type=MessageAuthor.CONTACT, external_id="client-1",
        )
        self.conversation = self.message.conversation

    def _inbound(self, external_id):
        ingest_inbound(
            self.integration,
            InboundMessage(
                external_id=external_id, user_id="visitor-1", chat_id="chat-1",
                text="Можно записаться?", display_name="Visitor",
            ),
        )
        return Message.objects.get(
            author_type=MessageAuthor.CONTACT, external_id=external_id,
        )

    def _payload(self, message=None):
        message = message or self.message
        return OutboxEvent.objects.get(
            event_type=AI_TURN_REQUESTED, payload__messageId=message.id,
        ).payload

    def _mirror(self, suffix="1"):
        return accept_native_reply(
            event=NativeReplyEvent(
                integration_id=self.integration.id,
                provider=IntegrationProvider.GATEWAY,
                source_id="tg-native",
                external_chat_id="chat-1",
                event_id=f"native-event-{suffix}",
                external_message_id=f"native-msg-{suffix}",
                occurred_at=datetime(2026, 10, 12, tzinfo=UTC),
                text="Ответила в Telegram",
            ),
            context=self.context, origin=OriginClass.EXTERNAL_AUTHORIZED,
            author_user_id=self.owner.id,
        )

    def _start(self, message=None, revision=None):
        message = message or self.message
        if revision is None:
            revision = self._payload(message)["mirrorRevision"]
        with tenant_atomic(self.context):
            return _begin(
                message_id=message.id, user_id="visitor-1", is_new=False,
                context=self.context, mirror_revision=revision,
            )

    def _finish(self, turn, text="Старый ответ AI"):
        return _commit_if_current(
            turn=turn, context=self.context,
            persist=lambda: store_answer(
                turn=turn, context=self.context, text=text,
            ),
        )

    def _assert_no_stale_effects(self):
        self.assertFalse(Message.objects.filter(author_type=MessageAuthor.AI).exists())
        self.assertFalse(OutboxEvent.objects.filter(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
        ).exists())
        self.assertFalse(Message.objects.filter(
            system_event__in=(SystemEvent.AI_UNAVAILABLE, SystemEvent.AI_HANDED_OVER),
        ).exists())

