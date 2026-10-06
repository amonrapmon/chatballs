"""Цикл инструментов в ходе агента (SPEC-0023 R-11–R-13, R-15)."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.db.models import Sum
from django.test import SimpleTestCase, override_settings

from chatballs.ai.invocation import ChatJob
from chatballs.ai.models import LlmInvocation, LlmInvocationStatus
from chatballs.ai.provider.base import ChatMessage, ProviderRejected
from chatballs.ai.pseudonymization import Pseudonymizer
from chatballs.ai.tool_loop import (
    ANSWER_WITHOUT_TOOLS,
    MAX_TOOL_ROUNDS,
    TOOLS_ARE_DATA,
    run_tool_loop,
)
from chatballs.ai.tool_loop_testing import (
    COMPLETION_TOKENS,
    EMAIL,
    NAME,
    PROMPT_TOKENS,
    ScriptedProvider,
    ToolLoopTestCase,
    calls,
    error,
    says,
)
from chatballs.conversations.models import AiTurnState, Message, SystemEvent
from chatballs.events.models import OutboxEvent
from chatballs.integrations.external_server_testing import TOKEN
from chatballs.integrations.mcp_testing import UPSTREAM_SECRET
from chatballs.integrations.tool_client import ToolResponse

FULL_NAME = "Иванова Анна Сергеевна"
ADDRESS = "Москва, ул. Лесная, д. 5, кв. 12"
ORDER = {
    "status": "В пути",
    "customer": {"full_name": FULL_NAME, "email": EMAIL},
    "delivery_address": ADDRESS,
}
MCP_CALL = ("get_order_status", {"order_number": "10482"})
HTTP_CALL = ("shop_order", {"order_number": "10482"})
BOUND_EMAIL = {
    "name": "email", "type": "string", "required": True, "location": "query",
    "source": {"type": "contact", "field": "email"},
}
ORDER_NUMBER = {"name": "order_number", "type": "string", "required": True, "location": "path"}


def _json_response(data: object, status: int = 200) -> ToolResponse:
    body = json.dumps(data, ensure_ascii=False).encode()
    return ToolResponse(status=status, content_type="application/json", body=body, url="")


class McpToolLoopTests(ToolLoopTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._enable((self.mcp, "get_order_status"))
        self.server.call_result = {
            "content": [{"type": "text", "text": json.dumps(ORDER, ensure_ascii=False)}]
        }

    def test_full_name_and_address_stay_out_of_provider_and_return_to_the_client(self) -> None:
        provider = ScriptedProvider(
            calls(("get_order_status", {"order_number": "10482", "email": "[[client_email]]"})),
            says("[[client_name]], заказ в пути. Получатель: [[name_1]], адрес: [[address_1]]."),
        )

        send = self._run_turn(provider)

        # Токены в аргументах раскрыл сервер: инструмент получил настоящую почту.
        call = next(item for item in self.server.requests if item["rpc"] == "tools/call")
        self.assertEqual(
            call["params"], {"name": "get_order_status", "arguments": {"order_number": "10482", "email": EMAIL}}
        )
        # Модель увидела результат данными под маской…
        self.assertEqual(
            provider.tool_results(),
            [
                '{"status":"В пути","customer":{"full_name":"[[name_1]]","email":"[[client_email]]"},'
                '"delivery_address":"[[address_1]]"}'
            ],
        )
        system = [m.content for m in provider.requests[0].messages if m.role == "system"]
        self.assertIn(TOOLS_ARE_DATA, system)
        # …и ни ФИО, ни адрес, ни почта провайдеру не ушли.
        sent = provider.sent()
        for value in (FULL_NAME, "Иванова", "Сергеевна", NAME, ADDRESS, "Лесная", EMAIL):
            self.assertNotIn(value, sent)

        expected = f"{NAME}, заказ в пути. Получатель: {FULL_NAME}, адрес: {ADDRESS}."
        self.assertEqual(self._reply(), expected)
        self.assertEqual(send.call_args.kwargs["text"], expected)
        self.assertEqual(self.incoming.ai_turn_state, AiTurnState.DONE)

    def test_result_values_are_not_stored_in_invocations_or_events(self) -> None:
        self._run_turn(ScriptedProvider(calls(MCP_CALL), says("Получатель: [[name_1]].")))

        stored = repr(list(LlmInvocation.objects.values())) + repr(list(OutboxEvent.objects.values()))
        for value in (FULL_NAME, ADDRESS, "name_1", "[["):
            self.assertNotIn(value, stored)

    def test_every_round_is_in_the_llm_journal(self) -> None:
        self._run_turn(ScriptedProvider(calls(MCP_CALL), calls(MCP_CALL), says("Заказ в пути.")))

        rows = LlmInvocation.objects.filter(channel=self.channel, purpose="agent_chat")
        self.assertEqual(rows.count(), 3)
        self.assertEqual(
            rows.aggregate(total=Sum("total_tokens"))["total"],
            3 * (PROMPT_TOKENS + COMPLETION_TOKENS),
        )
        self.assertEqual(set(rows.values_list("status", flat=True)), {LlmInvocationStatus.SUCCESS})

    def test_after_five_rounds_the_model_is_told_to_answer_without_tools(self) -> None:
        provider = ScriptedProvider(*[calls(MCP_CALL)] * MAX_TOOL_ROUNDS, says("Заказ в пути."))

        self._run_turn(provider)

        self.assertEqual(MAX_TOOL_ROUNDS, 5)
        self.assertEqual(len(provider.requests), 6)
        for request in provider.requests[:5]:
            self.assertEqual([tool.name for tool in request.tools], ["get_order_status"])
            self.assertNotIn("tool_choice", request.params or {})
            self.assertNotIn(ANSWER_WITHOUT_TOOLS, [m.content for m in request.messages])
        final = provider.requests[5]
        self.assertEqual((final.messages[-1].role, final.messages[-1].content), ("system", ANSWER_WITHOUT_TOOLS))
        self.assertEqual(final.params["tool_choice"], "none")
        self.assertEqual(len(provider.tool_results()), 5)
        self.assertEqual(self._reply(), "Заказ в пути.")
        self.assertEqual(LlmInvocation.objects.filter(purpose="agent_chat").count(), 6)

    def test_model_that_keeps_calling_tools_hands_the_dialog_over(self) -> None:
        provider = ScriptedProvider(calls(MCP_CALL))

        self._run_turn(provider)

        self.assertEqual(len(provider.requests), 6)
        self.assertEqual(self.incoming.ai_turn_state, AiTurnState.FAILED)
        self.assertTrue(
            Message.objects.filter(
                conversation=self.conversation, system_event=SystemEvent.AI_UNAVAILABLE
            ).exists()
        )
        # Токены потрачены во всех шести обращениях — все они в журнале.
        self.assertEqual(LlmInvocation.objects.filter(purpose="agent_chat").count(), 6)

    def test_provider_failure_in_a_later_round_is_recorded_with_earlier_rounds(self) -> None:
        self._run_turn(ScriptedProvider(calls(MCP_CALL), ProviderRejected("provider is down")))

        rows = LlmInvocation.objects.filter(purpose="agent_chat").order_by("id")
        self.assertEqual(
            list(rows.values_list("status", flat=True)),
            [LlmInvocationStatus.SUCCESS, LlmInvocationStatus.ERROR],
        )
        self.assertEqual(self.incoming.ai_turn_state, AiTurnState.FAILED)

    def test_tool_errors_come_back_as_codes_without_the_foreign_body(self) -> None:
        cases = {
            "tool_error": {"call_result": {"isError": True, "content": [{"type": "text", "text": UPSTREAM_SECRET}]}},
            "unauthorized": {"token": "Bearer another-token"},
            "bad_response": {"token": TOKEN, "html": True},
        }
        for code, settings in cases.items():
            with self.subTest(code=code):
                for name, value in settings.items():
                    setattr(self.server, name, value)
                provider = ScriptedProvider(calls(MCP_CALL), says("Не удалось узнать статус."))

                self._run_turn(provider)

                self.assertEqual(provider.tool_results(), [error(code)])
                self.assertNotIn(UPSTREAM_SECRET, provider.sent())
                self.assertEqual(self._reply(), "Не удалось узнать статус.")
                self.assertEqual(self.incoming.ai_turn_state, AiTurnState.DONE)

    def test_unknown_tool_is_an_error_code_too(self) -> None:
        provider = ScriptedProvider(calls(("cancel_order", {"order_number": "10482"})), says("Не могу."))

        self._run_turn(provider)

        self.assertEqual(provider.tool_results(), [error("unknown_tool")])
        self.assertNotIn("tools/call", self.server.methods)


class HttpToolLoopTests(ToolLoopTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.shop = self._http(
            "Заказ в магазине", toolName="shop_order", parameters=[ORDER_NUMBER, BOUND_EMAIL]
        )
        self._enable((self.shop, ""))
        patcher = patch("chatballs.integrations.http_tool.fetch", return_value=_json_response(ORDER))
        self.fetch = patcher.start()
        self.addCleanup(patcher.stop)

    def test_bound_parameter_is_added_by_the_server_and_hidden_from_the_model(self) -> None:
        provider = ScriptedProvider(calls(HTTP_CALL), says("Адрес: [[address_1]]."))

        self._run_turn(provider)

        (tool,) = provider.requests[0].tools
        self.assertEqual((tool.name, list(tool.parameters["properties"])), ("shop_order", ["order_number"]))
        self.assertEqual(
            self.fetch.call_args.args[0],
            "https://shop.example.test/api/orders/10482?email=anna%40example.ru",
        )
        self.assertNotIn(EMAIL, provider.sent())
        self.assertEqual(self._reply(), f"Адрес: {ADDRESS}.")

    def test_tool_without_the_bound_value_is_not_offered(self) -> None:
        self.contact.email = ""
        self.contact.save(update_fields=["email"])
        provider = ScriptedProvider(says("Уточните номер заказа."))

        self._run_turn(provider)

        self.assertIsNone(provider.requests[0].tools)
        self.assertNotIn(TOOLS_ARE_DATA, [m.content for m in provider.requests[0].messages])

    def test_call_waits_thirty_seconds_at_most_and_never_past_the_turn_deadline(self) -> None:
        self._run_turn(ScriptedProvider(calls(HTTP_CALL), says("Готово.")))
        self.assertEqual(self.fetch.call_args.kwargs["timeout"], 30.0)

        # Сообщение пролежало в очереди: до срока хода осталось меньше 30 секунд.
        with override_settings(CHATBALLS_AI_TURN_DEADLINE_SECONDS=120):
            self._run_turn(ScriptedProvider(calls(HTTP_CALL), says("Готово.")), age=110)
        self.assertLessEqual(self.fetch.call_args.kwargs["timeout"], 10.0)
        self.assertGreater(self.fetch.call_args.kwargs["timeout"], 0)

    def test_timeout_and_server_failures_do_not_break_the_turn(self) -> None:
        cases = {
            "timeout": TimeoutError("timed out"),
            "unreachable": ConnectionRefusedError("refused"),
            "bad_response": _json_response({"detail": UPSTREAM_SECRET}, status=500),
            "not_found": _json_response({"detail": UPSTREAM_SECRET}, status=404),
            "unauthorized": _json_response({"detail": UPSTREAM_SECRET}, status=401),
        }
        for code, outcome in cases.items():
            with self.subTest(code=code):
                self.fetch.side_effect = [outcome]
                provider = ScriptedProvider(calls(HTTP_CALL), says("Сайт не ответил."))

                self._run_turn(provider)

                self.assertEqual(provider.tool_results(), [error(code)])
                self.assertNotIn(UPSTREAM_SECRET, provider.sent())
                self.assertEqual(self._reply(), "Сайт не ответил.")
                self.assertEqual(self.incoming.ai_turn_state, AiTurnState.DONE)

    def test_arguments_that_do_not_fit_are_an_error_code(self) -> None:
        provider = ScriptedProvider(calls(("shop_order", {"order_number": ["10482"]})), says("Не могу."))

        self._run_turn(provider)

        self.assertEqual(provider.tool_results(), [error("invalid_arguments")])
        self.fetch.assert_not_called()


class TurnDeadlineTests(SimpleTestCase):
    def _job(self, provider: ScriptedProvider) -> ChatJob:
        return ChatJob(
            provider=provider,
            model="scripted",
            messages=[ChatMessage(role="user", content="Где мой заказ?")],
            breaker_key=(0, 0),
            breaker_revision=0,
        )

    def test_loop_does_not_start_a_round_after_the_turn_deadline(self) -> None:
        provider = ScriptedProvider(says("Поздно."))

        result = run_tool_loop(self._job(provider), [], Pseudonymizer(), time_left=0)

        self.assertEqual(provider.requests, [])
        self.assertEqual(str(result.rounds[-1].error), "turn deadline passed")

    def test_deadline_that_passes_during_a_round_ends_the_turn(self) -> None:
        provider = ScriptedProvider(calls(MCP_CALL))
        with patch("chatballs.ai.tool_loop._left", side_effect=[5.0, -1.0, -1.0]):
            result = run_tool_loop(self._job(provider), [], Pseudonymizer(), time_left=5)

        # Раунд состоялся, инструмент уже не вызывался, второго раунда нет.
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual([record.error for record in result.tool_calls], ["unknown_tool"])
        self.assertIsNotNone(result.rounds[0].result)
        self.assertEqual(str(result.rounds[-1].error), "turn deadline passed")
