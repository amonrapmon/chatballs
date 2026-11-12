"""Список контактов: страницы, фильтры и порядок считает база.

Раньше endpoint перебирал все контакты организации со всеми их диалогами, а
браузер резал результат на страницы — при росте базы это неизбежно упиралось
в память и время ответа.
"""

from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.models import (
    ConnectionIdentity,
    Contact,
    Conversation,
    LifecycleState,
    Message,
    MessageAuthor,
)
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import (
    Integration,
    IntegrationKind,
    IntegrationProvider,
)
from chatballs.testing import TenantAPIClient as APIClient


class ClientsListPaginationTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.channel = Channel.objects.create(
            organization=self.organization, code="line", name="Линия"
        )
        self.other_channel = Channel.objects.create(
            organization=self.organization, code="shop", name="Магазин"
        )
        self.telegram = self._connection(IntegrationProvider.TELEGRAM, "bot", self.channel)
        self.email = self._connection(IntegrationProvider.EMAIL, "mail", self.other_channel)
        self.contacts = [self._client(f"Клиент {index:02d}") for index in range(30)]
        # Пятеро с открытым диалогом и почтовым каналом — для фильтров.
        self.open_clients = self.contacts[:5]
        for contact in self.open_clients:
            self._conversation(contact, self.email, self.other_channel, LifecycleState.OPEN)
        self.client = APIClient()
        self.client.login(username="owner@example.com", password="temporary-password")

    def _connection(self, provider: str, name: str, channel: Channel) -> Integration:
        return Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=provider,
            name=name,
            channel=channel,
        )

    def _conversation(self, contact, connection, channel, lifecycle) -> Conversation:
        conversation = Conversation.objects.create(
            organization=self.organization,
            channel=channel,
            connection=connection,
            contact=contact,
            lifecycle=lifecycle,
        )
        Message.objects.create(
            conversation=conversation, author_type=MessageAuthor.CONTACT, text="Здравствуйте"
        )
        return conversation

    def _client(self, name: str) -> Contact:
        contact = Contact.objects.create(organization=self.organization, name=name)
        self._conversation(contact, self.telegram, self.channel, LifecycleState.CLOSED)
        return contact

    def _page(self, query: str = "") -> dict:
        response = self.client.get(f"/api/v1/conversations/clients/{query}")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_first_page_is_bounded(self) -> None:
        page = self._page()
        self.assertEqual(len(page["items"]), 20)
        self.assertEqual(page["total"], 30)
        self.assertEqual(page["pageCount"], 2)

    def test_contact_without_conversations_is_not_a_client(self) -> None:
        Contact.objects.create(organization=self.organization, name="Никогда не писал")
        self.assertEqual(self._page()["total"], 30)

    def test_open_filter_is_applied_before_the_page(self) -> None:
        page = self._page("?open=1")
        self.assertEqual(page["total"], len(self.open_clients))
        self.assertTrue(all(item["openDialogs"] > 0 for item in page["items"]))

    def test_channel_filter_is_applied_before_the_page(self) -> None:
        page = self._page("?channel=EMAIL")
        self.assertEqual(page["total"], len(self.open_clients))

    def test_agent_filter_is_applied_before_the_page(self) -> None:
        page = self._page(f"?agent={self.other_channel.id}")
        self.assertEqual(page["total"], len(self.open_clients))

    def test_dialog_counts_survive_filtering(self) -> None:
        # Счётчики считаются подзапросом: фильтр по каналу не должен их урезать.
        item = self._page("?channel=EMAIL")["items"][0]
        self.assertEqual(item["totalDialogs"], 2)
        self.assertEqual(item["openDialogs"], 1)

    def test_search_matches_name(self) -> None:
        page = self._page("?q=Клиент 07")
        self.assertEqual(page["total"], 1)

    def test_sort_by_open_dialogs(self) -> None:
        page = self._page("?sort=open")
        self.assertTrue(page["items"][0]["openDialogs"] >= page["items"][-1]["openDialogs"])

    def test_connector_platforms_and_account_identities(self) -> None:
        contact = Contact.objects.create(organization=self.organization, name="Connector Person")
        telegram_a = self._connection(IntegrationProvider.API_CONNECTOR, "TG branch A", self.channel)
        telegram_b = self._connection(IntegrationProvider.API_CONNECTOR, "TG branch B", self.channel)
        max_connection = self._connection(IntegrationProvider.API_CONNECTOR, "MAX branch", self.channel)
        for connection, service in (
            (telegram_a, "green_api_telegram"),
            (telegram_b, "green_api_telegram"),
            (max_connection, "green_api_max"),
        ):
            connection.config = {"connector_service": service}
            connection.save(update_fields=["config"])
            self._conversation(contact, connection, self.channel, LifecycleState.CLOSED)
            ConnectionIdentity.objects.create(
                contact=contact, connection=connection, external_user_id="same-external-user"
            )

        page = self._page("?q=Connector Person&channel=TG")
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["channels"], ["MAX", "TG"])
        self.assertEqual(self._page("?q=Connector Person&channel=MAX")["total"], 1)
        self.assertEqual(self._page("?q=Connector Person&channel=WEB")["total"], 0)
        from chatballs.conversations.client_details import client_detail
        detail = client_detail(self.organization.id, contact.id)
        self.assertEqual(detail["channels"], ["MAX", "TG"])
        self.assertEqual(len(detail["identities"]), 3)
        self.assertEqual(
            {row["integrationName"] for row in detail["identities"]},
            {"TG branch A", "TG branch B", "MAX branch"},
        )
        self.assertEqual(
            {row["displayProvider"] for row in detail["identities"]}, {"TELEGRAM", "MAX"},
        )

    def test_unknown_connector_is_generic_not_web(self) -> None:
        contact = Contact.objects.create(organization=self.organization, name="Unknown Connector")
        connection = self._connection(IntegrationProvider.API_CONNECTOR, "custom", self.channel)
        connection.config = {"connector_service": "custom_adapter"}
        connection.save(update_fields=["config"])
        self._conversation(contact, connection, self.channel, LifecycleState.CLOSED)
        page = self._page("?q=Unknown Connector&channel=API_CONNECTOR")
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["channels"], ["API_CONNECTOR"])
        self.assertEqual(self._page("?q=Unknown Connector&channel=WEB")["total"], 0)
