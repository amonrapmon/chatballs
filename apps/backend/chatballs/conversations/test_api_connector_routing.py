"""API Connector conversations are isolated by integration and chat route."""

from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.contacts_merge import merge_contacts
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import ConnectionIdentity, Conversation, LifecycleState
from chatballs.conversations.transports.base import InboundMessage
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import HumanUser, Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.tenancy.database import tenant_atomic


class APIConnectorRoutingTests(TestCase):
    def setUp(self):
        bootstrap_owner(email="connector-route-owner@example.com", password="Temporary-Test-Password!")
        self.organization = Organization.objects.get(slug="demo")
        self.channel = Channel.objects.create(
            organization=self.organization, name="Поддержка платформы", code="support",
        )
        self.a = self.connection("a")
        self.b = self.connection("b")

    def connection(self, name, provider=IntegrationProvider.API_CONNECTOR):
        return Integration.objects.create(
            organization=self.organization, kind=IntegrationKind.MESSENGER,
            provider=provider, name=name, channel=self.channel,
        )

    def ingest(self, connection, event, *, user="user-7", chat="chat-7"):
        with tenant_atomic(self.organization.id):
            ingest_inbound(connection, InboundMessage(
                external_id=event, user_id=user, chat_id=chat,
                text="Hello " + event, display_name="Test guest",
            ))

    def test_merged_contact_keeps_account_specific_routes(self):
        # Provider event, user and chat IDs may collide across connections.
        self.ingest(self.a, "same-id")
        self.ingest(self.b, "same-id")
        a = Conversation.objects.get(connection=self.a)
        b = Conversation.objects.get(connection=self.b)
        self.assertNotEqual(a.id, b.id)
        actor = HumanUser.objects.get(email="connector-route-owner@example.com")
        with tenant_atomic(self.organization.id):
            merge_contacts(
                organization=self.organization, target_id=a.contact_id,
                source_id=b.contact_id, reason="Same real-world person",
                actor=actor,
            )
        self.ingest(self.a, "later-a")
        self.ingest(self.b, "later-b")
        self.assertEqual(Conversation.objects.filter(channel=self.channel).count(), 2)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(a.contact_id, b.contact_id)
        self.assertEqual((a.connection_id, a.external_chat_id), (self.a.id, "chat-7"))
        self.assertEqual((b.connection_id, b.external_chat_id), (self.b.id, "chat-7"))
        self.assertEqual(a.route_external_user_id, "user-7")
        self.assertEqual(b.route_external_user_id, "user-7")
        self.assertEqual(a.messages.count(), 2)
        self.assertEqual(b.messages.count(), 2)

    def test_distinct_chats_and_reopened_route(self):
        self.ingest(self.a, "e1", chat="one")
        self.ingest(self.a, "e2", chat="two")
        self.ingest(self.a, "e3", chat="one")
        old = Conversation.objects.get(connection=self.a, external_chat_id="one")
        other = Conversation.objects.get(connection=self.a, external_chat_id="two")
        self.assertEqual(old.messages.count(), 2)
        self.assertEqual(other.messages.count(), 1)
        old.lifecycle = LifecycleState.CLOSED
        old.save(update_fields=["lifecycle"])
        self.ingest(self.a, "e4", chat="one")
        new = Conversation.objects.get(
            connection=self.a, external_chat_id="one", lifecycle=LifecycleState.OPEN,
        )
        self.assertEqual(new.previous_conversation_id, old.id)
        self.assertNotEqual(new.previous_conversation_id, other.id)

    def test_empty_or_oversized_route_cannot_create_conversation(self):
        for i, (user, chat) in enumerate([
            ("guest", ""), ("guest", " "), ("", "room"),
            ("guest", "r" * 129), ("g" * 129, "room"),
        ]):
            with self.subTest(i=i), self.assertRaises(ValueError):
                self.ingest(self.a, f"invalid-{i}", user=user, chat=chat)
        self.assertFalse(Conversation.objects.exists())
        self.assertFalse(ConnectionIdentity.objects.exists())

    def test_existing_native_lookup_is_unmodified(self):
        native_a = self.connection("native-a", IntegrationProvider.TELEGRAM)
        native_b = self.connection("native-b", IntegrationProvider.TELEGRAM)
        self.ingest(native_a, "native-1", chat="one")
        existing = Conversation.objects.get(connection=native_a)
        ConnectionIdentity.objects.create(
            connection=native_b, contact=existing.contact,
            external_user_id="user-7", display_name="Test guest",
        )
        self.ingest(native_b, "native-2", chat="two")
        self.assertEqual(Conversation.objects.filter(contact=existing.contact).count(), 1)
