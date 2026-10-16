from chatballs.ai.provider.base import ChatResult, ProviderError
from chatballs.ai.runtime import run_agent_turn
from chatballs.i18n import t


def run_channel_turn(*, channel, message: str, history: list[dict] | None = None) -> ChatResult:
    """One AI turn for a processing channel (ADR-CHATBALLS-0023).

    AI-поведение канала целиком определяет его агент. Без активного агента
    AI-ответа нет: вызывающий код (ingest/support) обрабатывает ProviderError
    как «AI недоступен» и передаёт диалог оператору.
    """
    agent = getattr(channel, "ai_agent", None)
    from chatballs.identity.models import Organization
    from chatballs.identity.operation_modes import autonomous_allowed

    organization = Organization.objects.get(pk=channel.organization_id)
    if not autonomous_allowed(channel, organization=organization):
        raise ProviderError(t("channels.no_active_agent"))
    from chatballs.ai.execution_policy import execution_guard
    from chatballs.ai.provider.base import ProviderRejected
    from chatballs.channels.models import Channel
    from chatballs.tenancy.database import tenant_atomic

    version = organization.operation_mode_version

    def current():
        with tenant_atomic(organization.pk):
            latest = Organization.objects.get(pk=organization.pk)
            route = Channel.objects.select_related("ai_agent").get(pk=channel.pk, organization=latest)
            return latest.operation_mode_version == version and autonomous_allowed(route, organization=latest)

    with execution_guard(current):
        result = run_agent_turn(agent=agent, message=message, history=history, style_guard=True).result
        if not current():
            raise ProviderRejected("autonomous turn cancelled")
        return result
