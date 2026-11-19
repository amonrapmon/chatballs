from django.db.models import QuerySet

from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext


def integrations_for_context(context: TenantContext) -> QuerySet[Integration]:
    return (
        Integration.objects.filter(organization_id=context.organization_id)
        .select_related("channel", "web_chat_widget")
        .order_by("provider", "name")
    )


def integration_for_context(
    *, context: TenantContext, integration_id: int, lock: bool = False,
) -> Integration:
    rows = Integration.objects.select_related("channel", "web_chat_widget")
    if lock:
        rows = rows.select_for_update(of=("self",), no_key=True)
    return rows.get(
        id=integration_id,
        organization_id=context.organization_id,
    )
