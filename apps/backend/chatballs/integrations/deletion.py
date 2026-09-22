from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError

from chatballs.i18n import t
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext


class IntegrationInUse(Exception):
    """Интеграция связана с агентом или каналом и не может быть удалена."""


def delete_integration(*, context: TenantContext, integration: Integration) -> None:
    if integration.organization_id != context.organization_id:
        raise ValidationError({"integration": t("settings.integration_other_organization")})
    try:
        integration.delete()
    except ProtectedError as error:
        raise IntegrationInUse(t("settings.integration_in_use")) from error
