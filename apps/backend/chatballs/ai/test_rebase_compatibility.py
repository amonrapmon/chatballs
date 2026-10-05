"""Совместимость инструментов с режимами доступа к полям и готовыми токенами."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from chatballs.ai.invocation import prepare_chat
from chatballs.ai.provider.base import ChatMessage, ToolCall
from chatballs.ai.pseudonymization import Pseudonymizer, contact_known_values
from chatballs.ai.site_context import client_context_prompt
from chatballs.ai.test_chat_data import parse_test_client_data


class PreviewFieldAccessTests(SimpleTestCase):
    def test_masked_open_hidden_fields_keep_access_and_tool_bindings(self):
        fields = [
            {"key": "order", "label": "Заказ", "type": "string", "ai_access": "masked"},
            {"key": "amount", "label": "Сумма", "type": "number", "ai_access": "open"},
            {"key": "internal", "label": "Скрыто", "type": "string", "ai_access": "hidden"},
        ]
        connection = SimpleNamespace(id=10, config={"fields": fields})
        values = {"order": 'номер "А"\n42', "amount": 12, "internal": "internal-secret"}
        with patch("chatballs.ai.test_chat_data.Integration.objects.filter") as query:
            query.return_value.order_by.return_value = [connection]
            preview = parse_test_client_data(
                SimpleNamespace(id=2, organization_id=1),
                {"name": "Анна", "webFields": {"10": values}},
            )
        prompt = client_context_prompt(preview.context_fields, preview.pseudonymizer)
        self.assertIn("Имя: [[client_name]]", prompt)
        self.assertIn("Заказ: [[order]]", prompt)
        self.assertIn("Сумма: 12", prompt)
        self.assertNotIn("Скрыто", prompt)
        self.assertNotIn("internal-secret", prompt)
        self.assertNotIn("номер", prompt)
        # Скрытые данные остаются доступны только привязке HTTP-инструмента.
        self.assertEqual(preview.client.web_fields[10], values)
        self.assertEqual(preview.pseudonymizer.known_token("12"), "")
        self.assertEqual(preview.pseudonymizer.known_token("internal-secret"), "")
        self.assertEqual(preview.pseudonymizer.restore("[[order]]").text, values["order"])

    def test_contact_value_resembling_a_token_is_replaced_as_a_whole(self):
        name = "Анна [[чужой-токен]]"
        pseudonymizer = Pseudonymizer(contact_known_values(name=name, phone="+7 999 000-11-22"))
        prompt = client_context_prompt([
            ("Имя", name), ("Телефон", "+7 999 000-11-22"),
        ], pseudonymizer)
        self.assertIn("Имя: [[client_name]]", prompt)
        self.assertIn("Телефон: [[client_phone]]", prompt)
        self.assertNotIn("Анна", prompt)
        self.assertNotIn("чужой-токен", prompt)


class PreparedToolMessageTests(SimpleTestCase):
    def test_preparation_preserves_tool_links_and_already_masked_context(self):
        call = ToolCall(id="call-1", name="order_status", arguments={})
        trusted = ChatMessage(role="system", content="Имя: [[client_name]]", masked=True)
        messages = [
            trusted,
            ChatMessage(role="assistant", content="Анна", tool_calls=(call,)),
            ChatMessage(role="tool", content="Анна", tool_call_id=call.id),
        ]
        with (
            patch("chatballs.ai.invocation.breaker_identity", return_value=((1, 2), 0)),
            patch("chatballs.ai.invocation.get_provider"),
        ):
            job = prepare_chat(
                channel=SimpleNamespace(), messages=messages, model="demo",
                pseudonymizer=Pseudonymizer(contact_known_values(name="Анна")),
            )
        self.assertIs(job.messages[0], trusted)
        self.assertEqual(job.messages[1].tool_calls, (call,))
        self.assertEqual(job.messages[2].tool_call_id, call.id)
        for item in job.messages[1:]:
            self.assertEqual(item.content, "[[client_name]]")
            self.assertTrue(item.masked)
        self.assertEqual(messages[1].content, "Анна")
