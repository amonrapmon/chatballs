from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class AgentTool(TenantRelationModel):
    """Инструмент внешнего сервера, включённый агенту (SPEC-0023 R-9).

    Строка есть только у включённого инструмента. У MCP-сервера ``tool_name`` —
    имя из снимка; HTTP-запрос — сам один инструмент, и имя у него пустое:
    переименование запроса не должно выключать его у агентов.
    """

    tenant_relation_fields = ("agent", "integration")

    agent = models.ForeignKey("ai.AIAgent", on_delete=models.CASCADE, related_name="tools")
    integration = models.ForeignKey(
        "integrations.Integration", on_delete=models.CASCADE, related_name="agent_tools"
    )
    tool_name = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["integration_id", "tool_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["agent", "integration", "tool_name"], name="uniq_agent_tool"
            ),
        ]

    def __str__(self) -> str:
        return f"agent-tool:{self.agent_id}/{self.integration_id}/{self.tool_name}"
