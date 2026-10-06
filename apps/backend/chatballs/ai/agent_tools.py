"""Инструменты агента: что ему доступно и что включено (SPEC-0023 R-9).

Включается только инструмент, который читает, и только у включённого сервера.
Как только инструмент перестаёт под это подходить — сервер выключили, сняли
подтверждение, инструмент пропал из списка, — он выключается у всех агентов.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError

from chatballs.ai.models import AgentTool, AIAgent
from chatballs.i18n import t
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.integrations.read_only import ServerTool, server_tools


def _servers(organization_id: int):
    return Integration.objects.filter(
        organization_id=organization_id, kind=IntegrationKind.EXTERNAL_SERVER
    ).order_by("name", "id")


def agent_tools_payload(agent: AIAgent) -> list[dict[str, object]]:
    """Внешние серверы организации с инструментами и отметкой, включён ли каждый."""
    enabled = set(agent.tools.values_list("integration_id", "tool_name"))
    return [
        {
            "integrationId": server.id,
            "name": server.name,
            "type": server.provider.lower(),
            "isActive": server.is_active,
            "status": server.status,
            "lastError": server.last_error,
            # Что именно сломалось и когда это заметили: причина в блоке «Инструменты».
            "lastErrorCode": server.last_error_code,
            "lastCheckedAt": (
                server.last_checked_at.isoformat() if server.last_checked_at else None
            ),
            "tools": [
                {
                    "name": tool.name,
                    "title": tool.title,
                    "description": tool.description,
                    "readOnly": tool.read_only,
                    "enabled": (server.id, tool.key) in enabled,
                }
                for tool in server_tools(server)
            ],
        }
        for server in _servers(agent.organization_id)
    ]


def _requested_tool(server: Integration | None, name: object) -> ServerTool:
    """Инструмент из запроса, если его можно включить агенту."""
    if server is None:
        raise ValidationError({"tools": t("ai.agent_tool_not_found")})
    tools = server_tools(server)
    if server.provider == IntegrationProvider.HTTP:
        tool = tools[0]
    else:
        tool = next((item for item in tools if item.name == name), None)
    if tool is None:
        raise ValidationError({"tools": t("ai.agent_tool_not_found")})
    if not server.is_active:
        raise ValidationError({"tools": t("ai.agent_tool_server_disabled", server=server.name)})
    if not tool.read_only:
        key = (
            "ai.agent_tool_post_not_read_only"
            if server.provider == IntegrationProvider.HTTP
            else "ai.agent_tool_may_change_data"
        )
        raise ValidationError({"tools": t(key, tool=tool.title)})
    return tool


def set_agent_tools(*, agent: AIAgent, raw: object) -> None:
    """Заменить набор включённых инструментов агента; вызывается в транзакции."""
    if not isinstance(raw, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get("integrationId"), int)
        and not isinstance(item.get("integrationId"), bool)
        for item in raw
    ):
        raise ValidationError({"tools": t("ai.agent_tools_invalid")})
    # Блокировка серверов: выключение сервера не разойдётся с включением инструмента.
    servers = {
        server.id: server
        for server in _servers(agent.organization_id)
        .filter(id__in=[item["integrationId"] for item in raw])
        .select_for_update()
    }
    wanted = {
        (item["integrationId"], _requested_tool(servers.get(item["integrationId"]), item.get("name")).key)
        for item in raw
    }
    current = set(agent.tools.values_list("integration_id", "tool_name"))
    for integration_id, tool_name in current - wanted:
        agent.tools.filter(integration_id=integration_id, tool_name=tool_name).delete()
    for integration_id, tool_name in sorted(wanted - current):
        AgentTool.objects.create(agent=agent, integration=servers[integration_id], tool_name=tool_name)


def drop_unavailable_tools(integration: Integration) -> None:
    """Выключить у всех агентов инструменты сервера, которые больше нельзя включить."""
    enabled = AgentTool.objects.filter(integration=integration)
    if integration.is_active:
        allowed = [tool.key for tool in server_tools(integration) if tool.read_only]
        enabled = enabled.exclude(tool_name__in=allowed)
    enabled.delete()
