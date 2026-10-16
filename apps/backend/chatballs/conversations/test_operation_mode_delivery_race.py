"""The external handoff and mode transition serialize on the real database."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

from django.db import close_old_connections, transaction
from django.test import TransactionTestCase

from chatballs.ai.models import AIAgent
from chatballs.channels.models import Channel
from chatballs.conversations.ai_reply_delivery import deliver_saved
from chatballs.conversations.models import Contact, Conversation, Message
from chatballs.identity.models import HumanUser, Organization, OrganizationMembership
from chatballs.identity.operation_modes import change_operation_mode, lock_organization
from chatballs.integrations.models import Integration
from chatballs.testing import tenant_context_for


class OperationModeDeliveryRaceTests(TransactionTestCase):
    def setUp(self):
        organization = Organization.objects.create(name="Race", slug="delivery-mode-race")
        user = HumanUser.objects.create_user(email="race@mode.test")
        OrganizationMembership.objects.create(organization=organization, user=user, role="OWNER")
        context = tenant_context_for(user)
        channel = Channel.objects.create(organization=organization, name="Route", code="route")
        provider = Integration.objects.create(organization=organization, name="Demo", kind="LLM_PROVIDER", provider="DEMO", secret="demo")
        AIAgent.objects.create(channel=channel, name="Agent", status="ACTIVE", provider_integration=provider)
        connection = Integration.objects.create(organization=organization, name="Web", kind="MESSENGER", provider="WEB", channel=channel)
        contact = Contact.objects.create(organization=organization, name="Customer")
        conversation = Conversation.objects.create(organization=organization, channel=channel, connection=connection,
                                                   contact=contact, control_mode="AI")
        source = Message.objects.create(conversation=conversation, author_type="CONTACT", text="Hi")
        self.organization, self.context = organization, context
        self.conversation, self.source, self.connection = conversation, source, connection

    def test_switch_waits_for_handoff_and_no_old_retry_starts_after_it(self):
        organization, context = self.organization, self.context
        conversation, source, connection = self.conversation, self.source, self.connection
        reply = Message.objects.create(conversation=conversation, author_type="AI", text="Hello", ai_reply_to=source,
                                       ai_delivery={"connectionId": connection.pk, "chatId": "chat", "userId": "user", "modeVersion": 1})
        entered, release, switching, switched = Event(), Event(), Event(), Event()

        def transport(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(10))
            return True

        def deliver():
            close_old_connections()
            try:
                deliver_saved(source.pk, context)
            finally:
                close_old_connections()

        def switch():
            close_old_connections()
            try:
                with transaction.atomic():
                    switching.set()
                    current = lock_organization(organization.pk)
                    change_operation_mode(context=context, organization=current, mode="OPERATORS_ONLY")
                switched.set()
            finally:
                close_old_connections()

        with patch("chatballs.conversations.transports.send_reply", side_effect=transport) as send:
            with ThreadPoolExecutor(max_workers=2) as executor:
                delivery = executor.submit(deliver)
                self.assertTrue(entered.wait(10))
                transition = executor.submit(switch)
                self.assertTrue(switching.wait(10))
                self.assertFalse(switched.wait(.1))
                release.set()
                delivery.result(timeout=15)
                transition.result(timeout=15)
            self.assertTrue(switched.is_set())
            deliver_saved(source.pk, context)
            self.assertEqual(send.call_count, 1)
        reply.refresh_from_db()
        self.assertTrue(reply.ai_delivery["sent"])

    def test_claim_and_switch_preserve_the_accepted_conversation_without_deadlock(self):
        from chatballs.conversations.access import require_independent_operation
        from chatballs.conversations.control_services import claim_conversation

        locked, switching = Event(), Event()
        def guard(*args, **kwargs):
            locked.set()
            self.assertTrue(switching.wait(10))
            return require_independent_operation(*args, **kwargs)

        def claim():
            close_old_connections()
            try:
                claim_conversation(context=self.context, conversation_id=self.conversation.pk)
            finally:
                close_old_connections()

        def switch():
            close_old_connections()
            try:
                self.assertTrue(locked.wait(10))
                with transaction.atomic():
                    organization = lock_organization(self.organization.pk)
                    switching.set()
                    change_operation_mode(context=self.context, organization=organization, mode="OPERATORS_ONLY")
            finally:
                close_old_connections()

        with patch("chatballs.conversations.control_services.require_independent_operation", side_effect=guard):
            with ThreadPoolExecutor(max_workers=2) as executor:
                acceptance = executor.submit(claim)
                transition = executor.submit(switch)
                acceptance.result(timeout=15)
                transition.result(timeout=15)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, "HUMAN")
        self.assertEqual(self.conversation.assigned_operator_id, self.context.actor_user.pk)

    def test_ingress_waits_for_switch_and_uses_its_committed_mode(self):
        from chatballs.conversations.ingest import ingest_inbound
        from chatballs.conversations.transports.base import InboundMessage

        locked, receiving = Event(), Event()
        def switch():
            close_old_connections()
            try:
                with transaction.atomic():
                    organization = lock_organization(self.organization.pk)
                    change_operation_mode(context=self.context, organization=organization, mode="OPERATORS_ONLY")
                    locked.set()
                    self.assertTrue(receiving.wait(10))
            finally:
                close_old_connections()

        def receive():
            close_old_connections()
            try:
                self.assertTrue(locked.wait(10))
                receiving.set()
                ingest_inbound(self.connection, InboundMessage(external_id="race", user_id="new-customer",
                               chat_id="new-chat", text="Hello", display_name="Customer"))
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            transition = executor.submit(switch)
            ingress = executor.submit(receive)
            transition.result(timeout=15)
            ingress.result(timeout=15)
        conversation = Conversation.objects.get(external_chat_id="new-chat")
        self.assertEqual(conversation.control_mode, "PAUSED")
        self.assertIsNotNone(conversation.waiting_since)
        self.assertFalse(conversation.messages.filter(ai_turn_state="PENDING").exists())

    def test_release_waits_for_switch_and_cannot_return_an_operator_dialog_to_ai(self):
        from chatballs.conversations.control_services import (
            ClaimError,
            claim_conversation,
            release_to_ai,
        )

        claim_conversation(context=self.context, conversation_id=self.conversation.pk)
        locked, returning = Event(), Event()
        def switch():
            close_old_connections()
            try:
                with transaction.atomic():
                    organization = lock_organization(self.organization.pk)
                    change_operation_mode(context=self.context, organization=organization, mode="OPERATORS_ONLY")
                    locked.set()
                    self.assertTrue(returning.wait(10))
            finally:
                close_old_connections()

        def release():
            close_old_connections()
            try:
                self.assertTrue(locked.wait(10))
                returning.set()
                with self.assertRaises(ClaimError):
                    release_to_ai(context=self.context, conversation_id=self.conversation.pk)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            transition = executor.submit(switch)
            handback = executor.submit(release)
            transition.result(timeout=15)
            handback.result(timeout=15)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, "HUMAN")
        self.assertEqual(self.conversation.assigned_operator_id, self.context.actor_user.pk)
