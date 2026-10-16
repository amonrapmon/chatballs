import json
import time
from dataclasses import replace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from chatballs.ai.invocation import ChatJob, run_chat
from chatballs.ai.operation_masking import masked_spec
from chatballs.ai.provider.base import ChatMessage, ProviderError, ToolSpec
from chatballs.ai.pseudonymization import KnownValue, Pseudonymizer
from chatballs.ai.tool_loop import MAX_CALL_BYTES, MAX_OPERATIONS, run_tool_loop, with_tools
from chatballs.ai.tool_loop_testing import ScriptedProvider, calls, says
from chatballs.ai.turn_skills import LOAD_SKILL, TurnSkill, TurnSkills


class SkillLoopTests(SimpleTestCase):
    def setUp(self):
        self.skills = TurnSkills((TurnSkill("skill-1", "Уточнение", "Когда нет номера", "Спросите номер"),))
        self.mask = Pseudonymizer()

    def job(self, provider):
        return with_tools(ChatJob(provider, "scripted", [ChatMessage("user", "Помогите")], (0, 0), 0),
                          [], self.mask, self.skills)

    def run_loop(self, provider, **kwargs):
        return run_tool_loop(self.job(provider), [], self.mask, skills=self.skills, **kwargs)

    def test_bad_selection_retries_inside_five_rounds_then_final_answer_without_badges(self):
        bad = calls((LOAD_SKILL, {"skill_id": "not-attached"}))
        provider = ScriptedProvider(*[bad] * 5, says("Уточните обращение"))
        result = self.run_loop(provider)
        self.assertEqual(len(result.rounds), 6)
        self.assertEqual(len(provider.requests), 6)
        self.assertEqual(provider.requests[-1].params["tool_choice"], "none")
        self.assertEqual(result.tool_calls, ())
        self.assertEqual([json.loads(value) for value in provider.tool_results()],
                         [{"error": "skill_unavailable"}] * 5)

    def test_model_ignoring_final_ban_stops_after_six_accounted_requests(self):
        provider = ScriptedProvider(calls((LOAD_SKILL, {"skill_id": "skill-1"})))
        result = self.run_loop(provider)
        self.assertEqual(len(result.rounds), 6)
        self.assertIsNotNone(result.rounds[-1].result)
        self.assertEqual(str(result.rounds[-1].error), "model kept calling tools after the round limit")
        self.assertEqual(result.tool_calls, ())

    def test_malformed_arguments_and_expired_internal_call_return_only_codes(self):
        for arguments in ([], {}, {"skill_id": 1}, {"skill_id": "skill-1", "extra": True}):
            self.assertEqual(json.loads(self.skills.load(arguments, self.mask)), {"error": "invalid_arguments"})
        self.assertEqual(json.loads(self.skills.load({"skill_id": "skill-1"}, self.mask, time_left=0)),
                         {"error": "timeout"})

    def test_batch_count_and_argument_volume_are_bounded_before_execution(self):
        for requests in (
            [(LOAD_SKILL, {"skill_id": "skill-1"})] * (MAX_OPERATIONS + 1),
            [(LOAD_SKILL, {"skill_id": "x" * MAX_CALL_BYTES})],
        ):
            provider = ScriptedProvider(calls(*requests))
            result = self.run_loop(provider)
            self.assertEqual(len(result.rounds), 1)
            self.assertEqual(str(result.rounds[-1].error), "operation limit exceeded")
            self.assertEqual(result.tool_calls, ())

    def test_repeated_loads_share_the_total_result_volume(self):
        provider = ScriptedProvider(calls((LOAD_SKILL, {"skill_id": "skill-1"}),
                                          (LOAD_SKILL, {"skill_id": "skill-1"})), says("Ответ"))
        with patch("chatballs.ai.tool_loop.MAX_OPERATION_BYTES", 82):
            result = self.run_loop(provider)
        self.assertIsNone(result.rounds[-1].error)
        self.assertEqual(json.loads(provider.tool_results()[-1]), {"error": "operation_volume_exceeded"})

    def test_no_more_requests_when_even_volume_error_exceeds_remaining_budget(self):
        provider = ScriptedProvider(calls((LOAD_SKILL, {"skill_id": "skill-1"})))
        with patch("chatballs.ai.tool_loop.MAX_OPERATION_BYTES", 1):
            result = self.run_loop(provider)
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(str(result.rounds[-1].error), "operation volume exceeded")

    def test_values_with_json_escapes_are_masked_before_serialization(self):
        name = 'Анна "Иванова"'
        self.mask = Pseudonymizer([KnownValue("client_name", name)])
        self.skills = TurnSkills((TurnSkill("skill-1", name, name, name),))
        provider = ScriptedProvider(calls((LOAD_SKILL, {"skill_id": "skill-1"})), says("Ответ"))
        self.run_loop(provider)
        self.assertEqual(json.loads(provider.tool_results()[0]), {"instruction": "[[client_name]]"})
        self.assertNotIn("Иванова", provider.sent())
        self.assertIn("[[client_name]]", provider.sent())

    def test_deadline_stops_loading_and_accounts_for_late_model_response(self):
        provider = ScriptedProvider(calls((LOAD_SKILL, {"skill_id": "skill-1"})))
        with (patch("chatballs.ai.tool_loop.run_chat", return_value=provider.steps[0]),
              patch("chatballs.ai.tool_loop.time.monotonic", side_effect=[0, 0, 0, 2, 2])):
            result = self.run_loop(provider, time_left=1)
        self.assertIsNotNone(result.rounds[-1].result)
        self.assertEqual(str(result.rounds[-1].error), "turn deadline passed")
        self.assertEqual(result.tool_calls, ())

    def test_schema_descriptions_and_values_use_the_same_turn_map(self):
        self.mask = Pseudonymizer([KnownValue("client_name", "Анна")])
        spec = ToolSpec("external", "Анна anna@example.test", {"type": "object", "properties": {
            "email": {"type": "string", "description": "anna@example.test", "default": "Анна"},
        }})
        masked = masked_spec(spec, self.mask)
        self.assertNotIn("Анна", repr(masked))
        self.assertNotIn("anna@example.test", repr(masked))
        self.assertIn("[[client_name]]", repr(masked))
        self.assertEqual(masked.name, "external")

    def test_masking_keeps_schema_keywords_and_catalog_ids_usable(self):
        mask = Pseudonymizer([KnownValue("client_name", "string")])
        spec = masked_spec(ToolSpec("lookup", "string", {"type": "object", "properties": {
            "string": {"type": "string", "description": "string"}}, "required": ["string"]}), mask)
        self.assertEqual(spec.parameters["properties"]["[[client_name]]"]["type"], "string")
        self.assertEqual(spec.parameters["required"], ["[[client_name]]"])
        id_ = "12345678-1234-1234-1234-123456789012"
        skills = TurnSkills((TurnSkill(id_, "Skill", "Condition", "Instruction"),))
        catalog_id = json.loads(skills.catalog(mask))[0]["id"]
        self.assertNotEqual(catalog_id, id_)
        self.assertEqual(json.loads(skills.load({"skill_id": catalog_id}, mask)), {"instruction": "Instruction"})

    @override_settings(CHATBALLS_AI_MAX_RETRIES=2)
    def test_provider_timeout_and_retry_backoff_cannot_exceed_turn_deadline(self):
        class TimedProvider(ScriptedProvider):
            timeout = 30

        provider = TimedProvider(says("Ответ"))
        job = self.job(provider)
        job = replace(job, deadline=time.monotonic() + 2)
        with patch.object(TimedProvider, "chat", autospec=True, return_value=says("Ответ")) as chat:
            run_chat(job)
        self.assertLessEqual(chat.call_args.args[0].timeout, 2)
        self.assertEqual(provider.timeout, 30)
        job = replace(job, deadline=time.monotonic() + 0.1, provider=TimedProvider(ProviderError("retry")))
        with patch("chatballs.ai.chat_execution.time.sleep") as sleep, self.assertRaisesMessage(ProviderError, "turn deadline passed"):
            run_chat(job)
        sleep.assert_not_called()
