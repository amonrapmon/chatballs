import json

from django.db import transaction
from django.utils.translation import override

from chatballs.conversations.ai_history import conversation_history
from chatballs.conversations.models import ConnectionIdentity, Message, MessageAuthor, SystemEvent
from chatballs.conversations.participant_notifications import (
    SPECIALIST_NOTICE_REQUESTED,
    customer_message_text,
)
from chatballs.conversations.participant_services import add_participant, remove_participant
from chatballs.conversations.participant_test_base import ParticipantTestBase
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.webchat.message_history import messages_payload
from chatballs.webchat.models import WebChatWidget, WebSession


class ParticipantNotificationTests(ParticipantTestBase):
    def setUp(self):
        self.members[1].user.full_name = "Мария"
        self.members[1].user.save(update_fields=["full_name"])
        self.organization.language = "ru"
        self.organization.save(update_fields=["language"])
        self.connection = Integration.objects.create(
            organization=self.organization, channel=self.conversation.channel,
            name="Web", kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.WEB,
        )
        self.conversation.connection = self.connection
        self.conversation.save(update_fields=["connection"])
        identity = ConnectionIdentity.objects.create(
            connection=self.connection, contact=self.conversation.contact,
            external_user_id="customer",
        )
        widget = WebChatWidget.objects.create(
            integration=self.connection, code="consultation", name="Consultation",
        )
        self.session = WebSession.objects.create(
            connection=self.connection, identity=identity, widget=widget,
            token_hash="a" * 64,
        )

    def add(self):
        return add_participant(
            context=self.context, conversation_id=self.conversation.pk,
            membership_id=self.members[1].pk, reason="CONFIDENTIAL: internal consultation",
        )[0]

    def notice(self):
        return Message.objects.get(system_event=SystemEvent.SPECIALIST_JOINED)

    def test_public_history_uses_approved_name_and_organization_language_without_reason(self):
        row = self.add()
        message = self.notice()
        self.assertEqual(message.author_type, MessageAuthor.SYSTEM)
        self.assertEqual(message.text, "")
        self.assertEqual(message.system_params, {"operator": "Мария"})
        with override("en"):
            payload = messages_payload(self.session, 0)
        self.assertEqual(payload["messages"][0]["text"], "К диалогу подключился специалист Мария.")
        self.assertEqual(payload["messages"][0]["author"], "system")
        self.assertNotIn("CONFIDENTIAL", json.dumps(payload))
        event = OutboxEvent.objects.get(event_type=SPECIALIST_NOTICE_REQUESTED)
        self.assertEqual(event.payload, {"messageId": message.pk})
        self.assertIsNone(event.membership_id)
        self.assertIsNone(event.actor_user_id)
        self.assertNotIn(row.join_reason, json.dumps(event.payload))
        Message.objects.create(conversation=self.conversation, author_type=MessageAuthor.CONTACT, text="Question")
        self.assertEqual(conversation_history(self.conversation, 20), [])

    def test_english_organization_notice_does_not_follow_operator_language(self):
        self.organization.language = "en"
        self.organization.save(update_fields=["language"])
        with override("ru"):
            self.add()
            self.assertEqual(customer_message_text(self.notice()), "Specialist Мария has joined the conversation.")
            self.assertEqual(messages_payload(self.session, 0)["messages"][0]["text"],
                             "Specialist Мария has joined the conversation.")

    def test_duplicate_add_remove_and_delivery_retry_do_not_duplicate_notice(self):
        row = self.add()
        self.add()
        remove_participant(
            context=self.context, conversation_id=self.conversation.pk,
            participant_id=row.pk, reason="CONFIDENTIAL: finished",
        )
        self.assertEqual(Message.objects.filter(system_event=SystemEvent.SPECIALIST_JOINED).count(), 1)
        event = OutboxEvent.objects.get(event_type=SPECIALIST_NOTICE_REQUESTED)
        # Real WEB transport: no external API replacement or test server.
        dispatch(event)
        self.assertEqual(self.notice().external_id, "specialist_notice:delivered")
        dispatch(event)
        self.assertEqual(Message.objects.filter(system_event=SystemEvent.SPECIALIST_JOINED).count(), 1)
        self.assertNotIn("CONFIDENTIAL", json.dumps(messages_payload(self.session, 0)))

    def test_rollback_removes_public_message_and_delivery_request(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.add()
            raise RuntimeError("Abort")
        self.assertFalse(Message.objects.filter(system_event=SystemEvent.SPECIALIST_JOINED).exists())
        self.assertFalse(OutboxEvent.objects.filter(event_type=SPECIALIST_NOTICE_REQUESTED).exists())
        self.assertFalse(self.conversation.participants.exists())

    def test_foreign_delivery_payload_cannot_deliver_another_tenants_notice(self):
        self.add()
        event = OutboxEvent.objects.get(event_type=SPECIALIST_NOTICE_REQUESTED)
        event.organization = self.foreign
        event.save(update_fields=["organization"])
        dispatch(event)
        self.assertEqual(self.notice().external_id, "")
