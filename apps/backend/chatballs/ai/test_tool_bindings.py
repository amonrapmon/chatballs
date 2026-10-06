"""Привязка параметров HTTP-инструмента к данным клиента диалога (SPEC-0023 R-4)."""

from __future__ import annotations

from chatballs.ai.tool_bindings import conversation_client_data, http_tool_spec
from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, ContactFieldValue, Conversation
from chatballs.integrations.external_server_testing import ExternalServerTestCase, order_status
from chatballs.integrations.http_tool import bound_arguments, build_request
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.testing import system_tenant_context

INCLUDE_ITEMS = {"name": "include_items", "type": "boolean", "location": "query"}


class ToolBindingTests(ExternalServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.channel = Channel.objects.create(organization=self.organization, code="site", name="Сайт")
        self.web = self._web("Сайт")
        self.contact = Contact.objects.create(
            organization=self.organization, name="Анна", email="anna@example.test", phone="+79990001122"
        )
        self.conversation = self._conversation(self.web)

    def _web(self, name: str) -> Integration:
        return create_integration(
            context=system_tenant_context(self.organization),
            data=IntegrationInput(
                provider=IntegrationProvider.WEB,
                name=name,
                channel_id=self.channel.id,
                config={
                    "allowedOrigins": ["shop.example.test"],
                    "fields": [{"key": "order_number", "label": "Номер заказа", "type": "string"}],
                },
            ),
        )

    def _conversation(self, connection: Integration | None) -> Conversation:
        return Conversation.objects.create(
            organization=self.organization,
            channel=self.channel,
            connection=connection,
            contact=self.contact,
        )

    def _value(self, value: object, *, web: Integration | None = None) -> None:
        ContactFieldValue.objects.create(
            organization=self.organization,
            contact=self.contact,
            integration=web or self.web,
            key="order_number",
            value=value,
        )

    def _tool(self, *parameters: dict) -> Integration:
        response = self._create("HTTP", order_status(parameters=list(parameters)))
        self.assertEqual(response.status_code, 201, response.content)
        return Integration.objects.get(id=response.json()["integration"]["id"])

    def _order_tool(self) -> Integration:
        source = {"type": "web_field", "integrationId": self.web.id, "key": "order_number"}
        return self._tool(
            {"name": "order_number", "type": "string", "location": "path", "source": source},
            INCLUDE_ITEMS,
        )

    def test_own_field_of_the_dialog_is_substituted_and_hidden_from_the_model(self) -> None:
        tool = self._order_tool()
        self._value("10482")
        client = conversation_client_data(self.conversation)

        spec = http_tool_spec(tool, client)

        self.assertEqual((spec.name, spec.description), ("get_order_status", "Статус заказа по номеру"))
        self.assertEqual(list(spec.parameters["properties"]), ["include_items"])
        self.assertEqual(spec.parameters["required"], [])
        request = build_request(
            tool, {"order_number": "999"}, bound_arguments(tool.config, client)
        )
        self.assertEqual(request.url, "https://shop.example.test/api/orders/10482")

    def test_tool_is_not_offered_without_the_value(self) -> None:
        tool = self._order_tool()

        self.assertIsNone(http_tool_spec(tool, conversation_client_data(self.conversation)))

    def test_own_field_is_not_bound_outside_the_web_widget(self) -> None:
        tool = self._order_tool()
        self._value("10482")
        telegram = Integration.objects.create(
            organization=self.organization,
            channel=self.channel,
            name="Telegram",
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.TELEGRAM,
        )
        other_web = self._web("Второй сайт")
        self._value("555", web=other_web)

        for connection in (telegram, other_web, None):
            with self.subTest(connection=connection):
                client = conversation_client_data(self._conversation(connection))
                self.assertIsNone(http_tool_spec(tool, client))

    def test_value_of_a_field_removed_from_the_connection_is_not_used(self) -> None:
        tool = self._order_tool()
        self._value("10482")
        self.web.config = {**self.web.config, "fields": []}
        self.web.save(update_fields=["config"])

        self.assertIsNone(http_tool_spec(tool, conversation_client_data(self.conversation)))

    def test_contact_fields_are_bound_in_a_dialog_of_any_connection(self) -> None:
        tool = self._tool(
            {"name": "order_number", "type": "string", "location": "path"},
            *(
                {"name": field, "type": "string", "required": True, "source": {"type": "contact", "field": field}}
                for field in ("name", "email", "phone")
            ),
        )
        client = conversation_client_data(self._conversation(None))

        spec = http_tool_spec(tool, client)

        self.assertEqual(list(spec.parameters["properties"]), ["order_number"])
        self.assertEqual(
            bound_arguments(tool.config, client),
            {"name": "Анна", "email": "anna@example.test", "phone": "+79990001122"},
        )

    def test_dialog_without_a_contact_has_no_bound_values(self) -> None:
        tool = self._tool(
            {"name": "order_number", "type": "string", "location": "path"},
            {"name": "email", "type": "string", "required": True, "source": {"type": "contact", "field": "email"}},
        )
        self.contact.email = ""
        self.contact.save(update_fields=["email"])

        self.assertIsNone(http_tool_spec(tool, conversation_client_data(self.conversation)))
        self.assertIsNone(http_tool_spec(tool, conversation_client_data(None)))
