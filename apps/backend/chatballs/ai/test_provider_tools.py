"""Вызов инструментов в провайдерах (SPEC-0023 R-10, R-11, R-14)."""

from unittest import mock

from django.test import SimpleTestCase

from chatballs.ai.provider import openai_http
from chatballs.ai.provider.base import (
    ChatMessage,
    ProviderError,
    ProviderRejected,
    ToolCall,
    ToolSpec,
)
from chatballs.ai.provider.custom import CustomProvider
from chatballs.ai.provider.demo import HANDOFF_TOKEN, DemoProvider
from chatballs.ai.provider.openrouter import OpenRouterProvider

ORDER_STATUS = ToolSpec(
    name="order_status",
    description="Статус заказа по номеру",
    parameters={
        "type": "object",
        "properties": {"order_number": {"type": "string", "description": "Номер заказа"}},
        "required": ["order_number"],
    },
)
SEARCH_PRODUCTS = ToolSpec(
    name="search_products",
    description="Поиск ноутбуков в каталоге",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}, "max_price": {"type": "number"}},
        "required": ["query", "max_price"],
    },
)
GET_PRICES = ToolSpec(name="get_prices", description="Цены на ноутбуки")


def _completion(message: dict) -> dict:
    return {
        "model": "vendor/model",
        "choices": [{"message": message}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5},
    }


def _chat(messages, *, response: dict, tools=None, params=None):
    with mock.patch.object(openai_http, "post_json", return_value=response) as post:
        result = openai_http.chat_completions(
            base_url="https://api.example.com/v1",
            api_key="sk-test",
            messages=messages,
            model="vendor/model",
            timeout=5,
            params=params,
            tools=tools,
        )
    return result, post.call_args.kwargs["payload"]


class ChatCompletionsToolsTests(SimpleTestCase):
    def test_request_carries_tools_in_openai_shape(self) -> None:
        _, payload = _chat(
            [ChatMessage(role="user", content="где мой заказ?")],
            response=_completion({"content": "ok"}),
            tools=[ORDER_STATUS, GET_PRICES],
        )
        self.assertEqual(
            payload["tools"][0],
            {
                "type": "function",
                "function": {
                    "name": "order_status",
                    "description": "Статус заказа по номеру",
                    "parameters": ORDER_STATUS.parameters,
                },
            },
        )
        # Инструмент без параметров уходит с пустой схемой объекта.
        self.assertEqual(
            payload["tools"][1]["function"]["parameters"], {"type": "object", "properties": {}}
        )

    def test_request_without_tools_has_no_tools_key(self) -> None:
        result, payload = _chat(
            [ChatMessage(role="user", content="привет")],
            response=_completion({"content": "ok"}),
        )
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["messages"], [{"role": "user", "content": "привет"}])
        self.assertEqual(result.text, "ok")
        self.assertEqual(result.tool_calls, ())

    def test_tool_calls_are_parsed_from_response(self) -> None:
        result, _ = _chat(
            [ChatMessage(role="user", content="где мой заказ 10482?")],
            response=_completion(
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "order_status",
                                "arguments": '{"order_number": "10482"}',
                            },
                        },
                        {
                            "id": "call_2",
                            "type": "function",
                            "function": {"name": "get_prices", "arguments": ""},
                        },
                    ],
                }
            ),
            tools=[ORDER_STATUS, GET_PRICES],
        )
        self.assertEqual(result.text, "")
        self.assertEqual(
            result.tool_calls,
            (
                ToolCall(id="call_1", name="order_status", arguments={"order_number": "10482"}),
                ToolCall(id="call_2", name="get_prices", arguments={}),
            ),
        )
        self.assertEqual(result.total_tokens, 17)

    def test_malformed_tool_arguments_are_a_provider_error(self) -> None:
        response = _completion(
            {
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "order_status", "arguments": "{oops"}}
                ],
            }
        )
        with self.assertRaises(ProviderError):
            _chat([ChatMessage(role="user", content="?")], response=response, tools=[ORDER_STATUS])

    def test_tool_round_is_sent_back_to_the_model(self) -> None:
        call = ToolCall(id="call_1", name="order_status", arguments={"order_number": "10482"})
        _, payload = _chat(
            [
                ChatMessage(role="user", content="где мой заказ 10482?"),
                ChatMessage(role="assistant", content="", tool_calls=(call,)),
                ChatMessage(role="tool", content='{"status":"в пути"}', tool_call_id="call_1"),
            ],
            response=_completion({"content": "Заказ в пути"}),
            tools=[ORDER_STATUS],
        )
        self.assertEqual(
            payload["messages"][1],
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "order_status",
                            "arguments": '{"order_number": "10482"}',
                        },
                    }
                ],
            },
        )
        self.assertEqual(
            payload["messages"][2],
            {"role": "tool", "tool_call_id": "call_1", "content": '{"status":"в пути"}'},
        )


class ToolSupportFlagTests(SimpleTestCase):
    """Признак поддержки инструментов моделью (R-10)."""

    def test_openrouter_reads_supported_parameters(self) -> None:
        provider = OpenRouterProvider(api_key="sk", base_url="https://openrouter.ai/api/v1")
        catalog = {
            "data": [
                {"id": "vendor/with-tools", "supported_parameters": ["temperature", "tools"]},
                {"id": "vendor/plain", "supported_parameters": ["temperature"]},
            ]
        }
        with mock.patch.object(openai_http, "get_json", return_value=catalog) as get:
            self.assertTrue(provider.supports_tools(model="vendor/with-tools"))
            self.assertFalse(provider.supports_tools(model="vendor/plain"))
            self.assertFalse(provider.supports_tools(model="vendor/unknown"))
        self.assertEqual(get.call_args.kwargs["path"], "/models")

    def test_openrouter_catalog_failure_is_a_provider_error(self) -> None:
        provider = OpenRouterProvider(api_key="sk", base_url="https://openrouter.ai/api/v1")
        with mock.patch.object(openai_http, "get_json", side_effect=ProviderError("down")):
            with self.assertRaises(ProviderError):
                provider.supports_tools(model="vendor/with-tools")

    def _custom(self) -> CustomProvider:
        return CustomProvider(api_key="sk", base_url="https://api.example.com/v1")

    def test_custom_endpoint_is_probed_with_a_tool_call(self) -> None:
        response = _completion(
            {
                "content": None,
                "tool_calls": [{"id": "c", "function": {"name": "ping", "arguments": "{}"}}],
            }
        )
        with mock.patch.object(openai_http, "post_json", return_value=response) as post:
            self.assertTrue(self._custom().supports_tools(model="local-model"))
        payload = post.call_args.kwargs["payload"]
        self.assertEqual(payload["model"], "local-model")
        self.assertEqual(payload["tools"][0]["function"]["name"], "ping")
        self.assertEqual(payload["tool_choice"]["function"]["name"], "ping")

    def test_custom_endpoint_without_tool_calls_does_not_support_tools(self) -> None:
        with mock.patch.object(
            openai_http, "post_json", return_value=_completion({"content": "pong"})
        ):
            self.assertFalse(self._custom().supports_tools(model="local-model"))

    def test_custom_endpoint_rejecting_tools_does_not_support_tools(self) -> None:
        with mock.patch.object(
            openai_http, "post_json", side_effect=ProviderRejected("HTTP 400: tools")
        ):
            self.assertFalse(self._custom().supports_tools(model="local-model"))

    def test_custom_endpoint_outage_is_a_provider_error(self) -> None:
        with mock.patch.object(openai_http, "post_json", side_effect=ProviderError("timeout")):
            with self.assertRaises(ProviderError):
                self._custom().supports_tools(model="local-model")


class DemoProviderToolsTests(SimpleTestCase):
    """Демо-провайдер имитирует цикл инструментов без сети и ключей (R-14)."""

    def _chat(self, messages, tools):
        # Сеть закрыта: любое обращение наружу уронило бы тест.
        with mock.patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            return DemoProvider().chat(messages=messages, model="demo", tools=tools)

    def test_calls_the_tool_matching_the_question(self) -> None:
        messages = [ChatMessage(role="user", content="Где мой заказ 10482?")]
        first = self._chat(messages, [ORDER_STATUS, SEARCH_PRODUCTS])
        self.assertEqual(
            first.tool_calls,
            (ToolCall(id="demo-0-0", name="order_status", arguments={"order_number": "10482"}),),
        )
        self.assertEqual(first.text, "")
        self.assertEqual(first, self._chat(messages, [ORDER_STATUS, SEARCH_PRODUCTS]))

    def test_answers_from_the_tool_result(self) -> None:
        call = ToolCall(id="demo-0-0", name="order_status", arguments={"order_number": "10482"})
        result = self._chat(
            [
                ChatMessage(role="user", content="Где мой заказ 10482?"),
                ChatMessage(role="assistant", content="", tool_calls=(call,)),
                ChatMessage(role="tool", content="Заказ в пути, курьер приедет с 14 до 16", tool_call_id=call.id),
            ],
            [ORDER_STATUS],
        )
        self.assertEqual(result.tool_calls, ())
        self.assertEqual(result.text, "Заказ в пути, курьер приедет с 14 до 16")
        self.assertNotIn(HANDOFF_TOKEN, result.text)

    def test_calls_several_tools_in_one_answer(self) -> None:
        result = self._chat(
            [ChatMessage(role="user", content="Нужен ноутбук до 80000 для монтажа")],
            [SEARCH_PRODUCTS, GET_PRICES, ORDER_STATUS],
        )
        self.assertEqual([call.name for call in result.tool_calls], ["search_products", "get_prices"])
        self.assertEqual(
            result.tool_calls[0].arguments, {"query": "80000", "max_price": 80000}
        )
        self.assertEqual([call.id for call in result.tool_calls], ["demo-0-0", "demo-0-1"])

    def test_pseudonymization_token_is_passed_as_argument(self) -> None:
        result = self._chat(
            [ChatMessage(role="user", content="Где мой заказ [[order_number]]?")], [ORDER_STATUS]
        )
        self.assertEqual(result.tool_calls[0].arguments, {"order_number": "[[order_number]]"})

    def test_tool_is_skipped_when_required_number_is_missing(self) -> None:
        result = self._chat(
            [ChatMessage(role="user", content="Нужен ноутбук для монтажа")], [SEARCH_PRODUCTS]
        )
        self.assertEqual(result.tool_calls, ())
        self.assertIn(HANDOFF_TOKEN, result.text)

    def test_unrelated_question_keeps_the_knowledge_reply(self) -> None:
        with_tools = self._chat(
            [ChatMessage(role="user", content="Есть ли у вас парковка?")], [ORDER_STATUS]
        )
        without_tools = self._chat([ChatMessage(role="user", content="Есть ли у вас парковка?")], None)
        self.assertEqual(with_tools, without_tools)
        self.assertEqual(with_tools.tool_calls, ())

    def test_demo_model_supports_tools(self) -> None:
        self.assertTrue(DemoProvider().supports_tools(model="demo"))
