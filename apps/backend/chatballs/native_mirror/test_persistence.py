"""PostgreSQL persistence and replay of native operator replies."""

from datetime import UTC, datetime
from unittest import mock
import uuid

from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.models import (
    ControlMode, Conversation, ExpectedResponder, Message, MessageAuthor,
)
from chatballs.events.models import OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import HumanUser, Organization, OrganizationMembership
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.native_mirror.classification import OriginClass
from chatballs.native_mirror.contracts import MirrorOutcome, NativeReplyEvent
from chatballs.native_mirror.models import (
    MirrorReceiptStatus, NativeMirrorConversationState, NativeMirrorReceipt,
)
from chatballs.native_mirror.service import NativeMirrorRejected, accept_native_reply
from chatballs.native_mirror.storage import NativeMirrorConflict
from chatballs.testing import system_tenant_context


class NativeMirrorPersistenceTests(TestCase):
    def setUp(self):
        bootstrap_owner(email="mirror@example.com", password="temporary-password")
        self.org = Organization.objects.get(slug="demo")
        self.user = HumanUser.objects.get(email="mirror@example.com")
        self.context = system_tenant_context(self.org)
        self.channel = Channel.objects.create(
            organization=self.org, code="mirror", name="Mirror"
        )
        self.integration = Integration.objects.create(
            organization=self.org, channel=self.channel,
            kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.GATEWAY,
            name="Gateway", secret="test",
            config={"source_id": "tg-main", "native_mirror_mode": "ENABLED"},
        )
        self.contact = self.org.contacts.create(name="Guest")
        self.conversation = self._conversation()

    def _conversation(self, *, contact=None):
        return Conversation.objects.create(
            organization=self.org, channel=self.channel, connection=self.integration,
            contact=contact or self.contact, external_chat_id="chat-1",
            control_mode=ControlMode.AI,
            expected_responder=ExpectedResponder.AI,
        )

    def event(self, **values):
        base = dict(
            integration_id=self.integration.id, provider=IntegrationProvider.GATEWAY,
            source_id="tg-main", external_chat_id="chat-1",
            event_id="event-1", external_message_id="msg-1",
            occurred_at=datetime(2026, 10, 12, 9, 0, tzinfo=UTC),
            text="Реплика оператора",
        )
        base.update(values)
        return NativeReplyEvent(**base)

    def accept(self, event=None, *, origin=OriginClass.EXTERNAL_AUTHORIZED, user_id=None):
        return accept_native_reply(
            event=event or self.event(), context=self.context,
            origin=origin,
            author_user_id=self.user.id if user_id is None and origin == OriginClass.EXTERNAL_AUTHORIZED
            else user_id,
        )

    def test_stores_message_and_revision_without_takeover_or_outbound(self):
        before_events = OutboxEvent.objects.count()
        result = self.accept()
        self.assertEqual(result.outcome, MirrorOutcome.STORED)
        message = Message.objects.get(id=result.message_id)
        self.assertEqual(message.author_type, MessageAuthor.OPERATOR)
        self.assertEqual(message.author_user_id, self.user.id)
        self.assertEqual(message.text, "Реплика оператора")
        self.assertEqual(message.external_id, "msg-1")
        self.assertIsNone(message.gateway_command_id)
        receipt = NativeMirrorReceipt.objects.get()
        self.assertEqual(receipt.status, MirrorReceiptStatus.STORED)
        self.assertEqual(receipt.pending_text, "")
        self.assertEqual(receipt.organization_id, self.org.id)
        self.assertEqual(receipt.message_id, message.id)
        self.assertEqual(
            NativeMirrorConversationState.objects.get(conversation=self.conversation).revision, 1
        )
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, ControlMode.AI)
        self.assertEqual(self.conversation.expected_responder, ExpectedResponder.AI)
        self.assertGreaterEqual(self.conversation.last_message_at, message.created_at)
        self.assertEqual(OutboxEvent.objects.count(), before_events)

    def test_identical_event_is_duplicate_without_revision_increment(self):
        first, second = self.accept(), self.accept()
        self.assertEqual(first.outcome, MirrorOutcome.STORED)
        self.assertEqual(second.outcome, MirrorOutcome.DUPLICATE)
        self.assertEqual(second.message_id, first.message_id)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 1)

    def test_same_text_with_new_provider_identity_is_not_a_duplicate(self):
        self.accept()
        other = self.accept(self.event(event_id="event-2", external_message_id="msg-2"))
        self.assertEqual(other.outcome, MirrorOutcome.STORED)
        self.assertEqual(Message.objects.count(), 2)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 2)

    def test_second_event_id_same_provider_message_does_not_duplicate(self):
        first = self.accept()
        second = self.accept(self.event(event_id="event-other"))
        self.assertEqual(second.outcome, MirrorOutcome.DUPLICATE)
        self.assertEqual(second.message_id, first.message_id)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(NativeMirrorReceipt.objects.count(), 1)

    def test_reused_event_id_with_changed_text_is_rejected(self):
        self.accept()
        with self.assertRaises(NativeMirrorConflict):
            self.accept(self.event(text="Другой текст"))
        self.assertEqual(Message.objects.count(), 1)

    def test_missing_dialogue_is_staged_then_replayed_with_full_text(self):
        self.conversation.delete()
        event = self.event()
        pending = self.accept(event)
        self.assertEqual(pending.outcome, MirrorOutcome.RETRYABLE)
        self.assertTrue(pending.retryable)
        receipt = NativeMirrorReceipt.objects.get()
        self.assertEqual(receipt.status, MirrorReceiptStatus.PENDING)
        self.assertEqual(receipt.pending_text, event.text)
        self.assertEqual(receipt.reason, "conversation_missing")
        self.assertFalse(Message.objects.exists())
        self.conversation = self._conversation()
        stored = self.accept(event)
        self.assertEqual(stored.outcome, MirrorOutcome.STORED)
        receipt.refresh_from_db()
        self.assertEqual(receipt.pending_text, "")
        self.assertEqual(receipt.message_id, stored.message_id)

    def test_alternative_event_id_can_replay_an_existing_pending_provider_message(self):
        self.conversation.delete()
        self.assertEqual(self.accept().outcome, MirrorOutcome.RETRYABLE)
        self.conversation = self._conversation()
        replay = self.accept(self.event(event_id="new-event-id"))
        self.assertEqual(replay.outcome, MirrorOutcome.STORED)
        self.assertEqual(NativeMirrorReceipt.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)

    def test_ambiguous_dialogue_is_a_retryable_recorded_outcome(self):
        extra_contact = self.org.contacts.create(name="Another")
        second = self._conversation(contact=extra_contact)
        pending = self.accept()
        self.assertEqual(pending.outcome, MirrorOutcome.UNMATCHED)
        self.assertTrue(pending.retryable)
        self.assertEqual(NativeMirrorReceipt.objects.get().reason, "conversation_ambiguous")
        self.assertFalse(Message.objects.exists())
        second.delete()
        self.assertEqual(self.accept().outcome, MirrorOutcome.STORED)

    def test_legacy_default_does_not_create_receipt_or_change_mode(self):
        self.integration.config = {"source_id": "tg-main"}
        self.integration.save(update_fields=["config"])
        self.assertEqual(self.accept().outcome, MirrorOutcome.IGNORED)
        self.assertFalse(NativeMirrorReceipt.objects.exists())
        self.assertFalse(NativeMirrorConversationState.objects.exists())

    def test_other_tenant_and_source_rejected(self):
        other = Organization.objects.create(name="Elsewhere", slug="elsewhere")
        with self.assertRaises(NativeMirrorRejected):
            accept_native_reply(
                event=self.event(), context=system_tenant_context(other),
                origin=OriginClass.EXTERNAL_AUTHORIZED, author_user_id=self.user.id,
            )
        with self.assertRaises(NativeMirrorRejected):
            self.accept(self.event(source_id="wrong"))
        self.assertFalse(NativeMirrorReceipt.objects.exists())

    def test_unverified_native_user_cannot_write_message(self):
        foreign = HumanUser.objects.create_user(email="outside@example.com")
        with self.assertRaises(NativeMirrorRejected):
            self.accept(user_id=foreign.id)
        self.assertFalse(NativeMirrorReceipt.objects.exists())

    def test_unknown_origin_is_audited_but_never_impersonates_staff(self):
        result = self.accept(origin=OriginClass.EXTERNAL_UNCLASSIFIED)
        self.assertEqual(result.outcome, MirrorOutcome.UNCLASSIFIED)
        receipt = NativeMirrorReceipt.objects.get()
        self.assertEqual(receipt.status, MirrorReceiptStatus.UNCLASSIFIED)
        self.assertEqual(receipt.pending_text, "")
        self.assertIsNone(receipt.author_user_id)
        self.assertFalse(Message.objects.exists())

    def test_gateway_self_echo_is_recorded_without_creating_operator_reply(self):
        own = Message.objects.create(
            conversation=self.conversation, author_type=MessageAuthor.AI,
            text="Наш ответ", gateway_command_id=uuid.uuid4(), external_id="msg-1",
        )
        result = self.accept(origin=OriginClass.SELF_ECHO)
        self.assertEqual(result.outcome, MirrorOutcome.SELF_ECHO)
        self.assertEqual(result.message_id, own.id)
        self.assertEqual(NativeMirrorReceipt.objects.get().status, MirrorReceiptStatus.SELF_ECHO)
        self.assertEqual(Message.objects.count(), 1)
        self.assertFalse(NativeMirrorConversationState.objects.exists())

    def test_unmatched_self_echo_is_unclassified_not_an_operator(self):
        result = self.accept(origin=OriginClass.SELF_ECHO)
        self.assertEqual(result.outcome, MirrorOutcome.UNCLASSIFIED)
        self.assertFalse(Message.objects.exists())

    def test_outbound_echo_cannot_be_mistaken_for_trusted_operator(self):
        Message.objects.create(
            conversation=self.conversation, author_type=MessageAuthor.AI,
            text="Наш ответ", gateway_command_id=uuid.uuid4(), external_id="msg-1",
        )
        result = self.accept()
        self.assertEqual(result.outcome, MirrorOutcome.SELF_ECHO)
        self.assertEqual(Message.objects.filter(author_type=MessageAuthor.OPERATOR).count(), 0)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 0)

    def test_error_after_message_insert_rolls_back_receipt_revision_and_message(self):
        original = NativeMirrorReceipt.save

        def fail_stored(instance, *args, **kwargs):
            if instance.status == MirrorReceiptStatus.STORED:
                raise RuntimeError("injected failure")
            return original(instance, *args, **kwargs)

        with (
            mock.patch.object(NativeMirrorReceipt, "save", fail_stored),
            self.assertRaises(RuntimeError),
        ):
            self.accept()
        self.assertFalse(Message.objects.exists())
        self.assertFalse(NativeMirrorReceipt.objects.exists())
        self.assertFalse(NativeMirrorConversationState.objects.exists())
        self.assertEqual(self.accept().outcome, MirrorOutcome.STORED)
