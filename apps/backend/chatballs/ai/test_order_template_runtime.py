"""Built-in skill through real runtime, with network boundaries confined to pytest."""

import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from chatballs.ai.models import AgentTool
from chatballs.ai.skill_runtime_testing import SkillRuntimeSetup
from chatballs.ai.skill_templates.order_basis import CARD_ID, STATUS_ID, order_basis
from chatballs.ai.tool_loop_testing import ScriptedProvider, calls, says
from chatballs.ai.turn_skills import LOAD_SKILL
from chatballs.ai.turn_templates import PREPARE_REPLY
from chatballs.conversations.models import Contact, Conversation, Message
from chatballs.integrations.models import Integration
from chatballs.integrations.tool_client import ToolResponse


class SourceReplyProvider(ScriptedProvider):
    def __init__(self, skill_id, template_id):
        self.skill_id, self.template_id = skill_id, template_id
        super().__init__(calls((LOAD_SKILL, {"skill_id": skill_id})), calls(("read_order", {})))

    def chat(self, *, messages, model, params=None, tools=None):
        if messages[-1].role == "tool":
            result = json.loads(messages[-1].content)
            if "final_response" in result:
                self.steps = [says(result["final_response"])]
            elif "currency" in result:
                fields = ("order_no", "items", "total") if self.template_id == CARD_ID else ("order_no", "status", "eta")
                self.steps = [calls((PREPARE_REPLY, {
                    "skill_id": self.skill_id, "template_id": self.template_id,
                    "data": {key: result[key] for key in fields if key in result},
                }))]
            elif "error" in result:
                self.steps = [says("Please ask a colleague. <<HANDOFF>>")]
        return super().chat(messages=messages, model=model, params=params, tools=tools)


@override_settings(CHATBALLS_AI_PROVIDER="", CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class OrderTemplateRuntimeTests(SkillRuntimeSetup, TestCase):
    def setUp(self):
        super().setUp()
        basis = order_basis(language="en")
        self.skill.instruction, self.skill.templates = basis["instruction"], basis["templates"]
        self.skill.save(update_fields=["instruction", "templates"])
        self.http = Integration.objects.create(
            organization=self.organization, kind="EXTERNAL_SERVER", provider="HTTP", name="Read orders",
            config={"tool_name": "read_order", "description": "Read an authorized customer's order",
                    "method": "GET", "url": "https://orders.example.test/read", "parameters": []},
        )
        AgentTool.objects.create(organization=self.organization, agent=self.agent, integration=self.http)

    def request(self, template_id, data):
        provider = SourceReplyProvider(str(self.skill.public_id), template_id)
        response_body = json.dumps(data).encode()
        with patch("chatballs.ai.invocation.get_provider", return_value=provider), patch(
            "chatballs.integrations.http_tool.fetch", return_value=ToolResponse(
                status=200, content_type="application/json", body=response_body, url="",
            ),
        ) as fetch:
            response = self.client.post(self.chat_url, {"message": "Read my order"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json(), provider, fetch

    def test_card_and_status_render_only_values_from_the_enabled_tool(self):
        cases = [
            (CARD_ID, {"currency": "RUB", "order_no": "T161-42", "items": [
                {"title": "Source garment", "qty": 2, "price": 321, "sum": 642},
            ], "total": 642}, "Source garment"),
            (STATUS_ID, {"currency": "RUB", "order_no": "T161-42", "status": "Source packed"}, "Source packed"),
        ]
        for template_id, data, expected in cases:
            with self.subTest(template=template_id):
                response, provider, fetch = self.request(template_id, data)
                fetch.assert_called_once()
                self.assertIn(expected, response["reply"])
                self.assertIn(expected, response["contentHtml"])
                self.assertEqual(response["template"]["id"], template_id)
                self.assertNotIn('class="eta"', response["contentHtml"])
                self.assertEqual([call["name"] for call in response["toolCalls"]], ["read_order"])
                self.assertNotIn("examples", provider.sent())
        for model in (Contact, Conversation, Message):
            self.assertFalse(model.objects.exists())

    def test_missing_or_unavailable_source_never_substitutes_editor_examples(self):
        response, _, fetch = self.request(CARD_ID, {"currency": "RUB", "order_no": "T161-42"})
        fetch.assert_called_once()
        self.assertNotIn("presentation", response)
        self.assertIn("<<HANDOFF>>", response["reply"])
        self.agent.tools.all().delete()
        response, _, fetch = self.request(STATUS_ID, {"currency": "RUB", "order_no": "T161-42", "status": "Unavailable"})
        fetch.assert_not_called()
        self.assertNotIn("presentation", response)
        self.assertIn("<<HANDOFF>>", response["reply"])
        self.assertIn("Examples are design-only", self.skill.instruction)
