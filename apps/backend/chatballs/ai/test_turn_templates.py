import json
from unittest.mock import patch

from django.test import SimpleTestCase

from chatballs.ai.invocation_jobs import ChatJob
from chatballs.ai.prepared_reply import PREPARED_PREFIX
from chatballs.ai.provider.base import ChatMessage, ProviderError, ToolSpec
from chatballs.ai.pseudonymization import KnownValue, Pseudonymizer
from chatballs.ai.template_diagnostics import without_operation_data
from chatballs.ai.template_runtime_testing import TEMPLATE_ID, SelectingProvider, reply_template
from chatballs.ai.tool_loop import run_tool_loop, with_tools
from chatballs.ai.tool_loop_testing import ScriptedProvider, calls, says
from chatballs.ai.turn_skills import LOAD_SKILL, TurnSkill, TurnSkills, encoded
from chatballs.ai.turn_templates import PREPARE_REPLY, TurnTemplates
from chatballs.ai.turn_tools import TurnTool


class TurnTemplateTests(SimpleTestCase):
    def setUp(self):
        self.pseudo = Pseudonymizer([KnownValue("client_name", '<b>Anna & "Co"</b>')])
        self.template = reply_template()
        self.skill = TurnSkill("skill", "Skill", "When needed", "Use trustworthy data", 7,
                               (encoded(self.template),))
        self.skills = TurnSkills((self.skill,))
        self.runtime = TurnTemplates(self.skills, [], self.pseudo, language="en")
        self.arguments = {"skill_id": "skill", "template_id": TEMPLATE_ID,
                          "data": {"title": "[[client_name]]", "amount": 0, "active": False}}

    def load(self):
        return json.loads(self.runtime.load({"skill_id": "skill"}, time_left=30))

    def prepare(self, **changes):
        return json.loads(self.runtime.prepare({**self.arguments, **changes}, time_left=30))

    def test_load_is_metadata_only_and_preparation_requires_loaded_snapshot(self):
        self.assertEqual(self.prepare(), {"error": "template_unavailable"})
        payload = self.load()
        self.assertEqual(set(payload["templates"][0]), {"id", "name", "purpose", "schema"})
        self.assertNotIn(self.template["html"], encoded(payload))
        self.assertNotIn(self.template["css"], encoded(payload))
        for changes in ({"skill_id": "foreign"}, {"template_id": "unknown"}):
            self.assertEqual(self.prepare(**changes), {"error": "template_unavailable"})
        selected = self.runtime.select(self.prepare()["final_response"])
        self.assertIn("&lt;b&gt;Anna &amp;", selected.content_html)
        self.assertIn('<b>Anna & "Co"</b>', selected.text)
        self.assertIn("0", selected.text)
        self.assertEqual(json.loads(selected.template_json)["skillRevision"], 7)
        self.assertNotIn("data", selected.payload())
        with self.assertRaises(ProviderError):
            self.runtime.select("prefix " + next(iter(self.runtime.prepared)))

    def test_unknown_damaged_tokens_and_wrong_types_never_prepare(self):
        self.load()
        for bad in ("[[unknown]]", "[[client_name", "client_name]]", "known [[missing]] rest"):
            for key in ("title", "url"):
                data = {**self.arguments["data"], key: bad}
                self.assertEqual(self.prepare(data=data)["error"], "invalid_template_data")
        for data in ({"title": "", "amount": 1, "active": True},
                     {**self.arguments["data"], "amount": "0"},
                     {**self.arguments["data"], "active": 0},
                     {**self.arguments["data"], "extra": "value"}):
            self.assertEqual(self.prepare(data=data)["error"], "invalid_template_data")
        token = self.pseudo.tokenize("number", "123456789012")
        result = self.prepare(data={**self.arguments["data"], "amount": token})
        self.assertIn("final_response", result)
        self.assertIn("123", self.runtime.select(result["final_response"]).text)

    def test_restored_unsafe_url_is_rejected_before_final_sanitization(self):
        self.load()
        token = self.pseudo.tokenize("address", 'javascript:alert(1)')
        result = self.prepare(data={**self.arguments["data"], "url": token})
        self.assertEqual(result["error"], "invalid_template_data")
        self.assertEqual(self.runtime.prepared, {})
        self.assertEqual(json.loads(self.runtime.prepare(self.arguments, time_left=0)), {"error": "timeout"})

    def job(self, provider):
        return with_tools(ChatJob(provider=provider, model="test", messages=[
            ChatMessage(role="user", content="Status"),
        ], breaker_key=(0, 0), breaker_revision=0), [], self.pseudo, self.skills)

    def test_loop_selects_exact_prepared_reply_and_can_choose_plain_text(self):
        steps = (calls((LOAD_SKILL, {"skill_id": "skill"})), calls((PREPARE_REPLY, self.arguments)))
        provider = SelectingProvider(*steps)
        loop = run_tool_loop(self.job(provider), [], self.pseudo, skills=self.skills, time_left=30)
        self.assertIsNotNone(loop.prepared_reply)
        self.assertEqual(loop.tool_calls, ())
        self.assertEqual(len(loop.rounds), 3)
        self.assertNotIn(loop.prepared_reply.content_html, provider.sent())
        provider = ScriptedProvider(*steps, says("Please clarify."))
        plain = run_tool_loop(self.job(provider), [], self.pseudo, skills=self.skills)
        self.assertIsNone(plain.prepared_reply)
        self.assertEqual(plain.rounds[-1].result.text, "Please clarify.")
        provider = ScriptedProvider(says(PREPARED_PREFIX + "unknown"))
        self.assertIsNotNone(run_tool_loop(self.job(provider), [], self.pseudo, skills=self.skills).rounds[-1].error)

    def test_failed_preparations_share_round_budget_and_names_do_not_collide(self):
        provider = ScriptedProvider(calls((PREPARE_REPLY, self.arguments)))
        loop = run_tool_loop(self.job(provider), [], self.pseudo, skills=self.skills)
        self.assertEqual(len(loop.rounds), 6)
        self.assertIsNotNone(loop.rounds[-1].error)
        tools = [TurnTool(ToolSpec(name=PREPARE_REPLY, description="external"), None, PREPARE_REPLY)]
        runtime = TurnTemplates(self.skills, tools, self.pseudo, language="en")
        self.assertEqual(runtime.operation, PREPARE_REPLY + "_1")
        with patch("chatballs.ai.turn_templates.time.monotonic", side_effect=[0, 31]):
            self.load()
            self.assertEqual(self.prepare(), {"error": "timeout"})

    def test_diagnostic_copy_omits_arguments_and_tool_results(self):
        original = {"messages": [{"role": "tool", "content": "SENSITIVE RESULT"},
                                 {"role": "assistant", "content": "SECRET", "tool_calls": [{"arguments": {"data": "SECRET"}}]}],
                    "text": "SECRET", "tool_calls": [{"arguments": {"data": "SECRET"}}]}
        cleaned = without_operation_data(original)
        self.assertNotIn("SECRET", encoded(cleaned))
        self.assertNotIn("SENSITIVE RESULT", encoded(cleaned))
        self.assertIn("SECRET", encoded(original))

    def test_schema_protocol_types_are_preserved_when_they_match_a_known_value(self):
        pseudo = Pseudonymizer([KnownValue("client_name", "string")])
        payload = json.loads(self.skills.load({"skill_id": "skill"}, pseudo))
        self.assertEqual(payload["templates"][0]["schema"]["properties"]["title"]["type"], "string")
