"""Инструменты хода: что из включённого агенту предложить модели (SPEC-0023 R-11).

Читается из базы один раз, в транзакции плана хода: сервер, описание для
модели и значения привязанных параметров. Сами вызовы идут потом, вне
транзакции (chatballs.ai.tool_loop).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from chatballs.ai.models import AIAgent
from chatballs.ai.provider.base import ToolSpec
from chatballs.ai.tool_bindings import conversation_client_data, http_tool_spec
from chatballs.ai.tool_support import cached_tool_support
from chatballs.conversations.models import Conversation
from chatballs.integrations.http_tool import ClientData, bound_arguments
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.integrations.read_only import ServerTool, server_tools

logger = logging.getLogger(__name__)

# Имя функции в формате OpenAI: другое провайдер отклонит вместе со всем запросом.
_MODEL_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True, slots=True)
class TurnTool:
    """Инструмент, готовый к вызову в этом ходе."""

    spec: ToolSpec
    integration: Integration
    # Название для людей: под ним вызов увидит оператор.
    title: str
    # Привязанные параметры HTTP-запроса: их подставляет сервер, модель не видит.
    bound: Mapping[str, object] = field(default_factory=dict)


def _mcp_spec(integration: Integration, name: str) -> ToolSpec | None:
    tool = next((tool for tool in integration.tools if tool["name"] == name), None)
    if tool is None:
        return None
    return ToolSpec(
        name=name,
        description=tool.get("description", ""),
        parameters=tool.get("input_schema") or {},
    )


def plan_turn_tools(
    *,
    agent: AIAgent,
    conversation: Conversation | None = None,
    client: ClientData | None = None,
) -> list[TurnTool]:
    """Шаг в транзакции: включённые агенту инструменты, пригодные в этом ходе.

    Не предлагаются: инструмент выключенного сервера, инструмент без отметки
    «только чтение» и HTTP-запрос без обязательного привязанного значения (R-4).
    Данные клиента по умолчанию берутся из диалога.
    """
    enabled = list(
        agent.tools.filter(integration__kind=IntegrationKind.EXTERNAL_SERVER).select_related(
            "integration"
        )
    )
    if not enabled:
        return []
    # Модель, про которую известно, что инструменты она не вызывает, отклонит запрос.
    if cached_tool_support(agent) is False:
        return []
    if client is None:
        client = conversation_client_data(conversation)
    readable: dict[int, dict[str, ServerTool]] = {}
    planned: dict[str, TurnTool] = {}
    for item in enabled:
        server = item.integration
        if not server.is_active:
            continue
        if server.id not in readable:
            readable[server.id] = {
                tool.key: tool for tool in server_tools(server) if tool.read_only
            }
        tool = readable[server.id].get(item.tool_name)
        if tool is None:
            continue
        if server.provider == IntegrationProvider.HTTP:
            spec = http_tool_spec(server, client)
            bound = bound_arguments(server.config, client) if spec is not None else None
        else:
            spec = _mcp_spec(server, item.tool_name)
            bound = {}
        if spec is None or bound is None:
            continue
        if not _MODEL_NAME.match(spec.name) or spec.name in planned:
            # Два инструмента с одним именем модель не различит: остаётся первый.
            logger.warning(
                "Tool %r of integration %s is not offered to the model: invalid or duplicate name",
                spec.name,
                server.id,
            )
            continue
        planned[spec.name] = TurnTool(
            spec=spec, integration=server, title=tool.title, bound=bound
        )
    return list(planned.values())
