"""Admin-only configuration, serialized with scheduling/delivery."""

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from chatballs.i18n import t
from chatballs.identity.audit import record_audit_event
from chatballs.identity.policy import ResourceScope, authorize
from chatballs.ratings.models import RatingRequest, RatingSettings
from chatballs.ratings.validation import validate_settings
from chatballs.tenancy.database import tenant_atomic

FIELDS = {"enabled": "enabled", "scale": "scale", "text": "text", "delaySeconds": "delay_seconds"}


def require_admin(context):
    if not authorize(context.membership, "settings.manage", ResourceScope(context.organization_id)):
        raise PermissionDenied(t("ratings.forbidden"))


def settings_payload(policy):
    return {name: getattr(policy, field) for name, field in FIELDS.items()}


def update_settings(context, data):
    with tenant_atomic(context):
        require_admin(context)
        if not isinstance(data, dict) or set(data) - FIELDS.keys():
            raise ValidationError(t("ratings.invalid_settings"))
        RatingSettings.objects.get_or_create(organization_id=context.organization_id)
        policy = RatingSettings.objects.select_for_update().get(organization_id=context.organization_id)
        for name, value in data.items():
            setattr(policy, FIELDS[name], value)
        validate_settings(policy)
        policy.save()
        if not policy.enabled:
            RatingRequest.objects.filter(
                organization_id=context.organization_id, sent_at__isnull=True, cancelled_at__isnull=True,
            ).update(cancelled_at=timezone.now())
        record_audit_event(
            action="ratings.settings_changed", actor=context.actor_user,
            organization=context.organization, object_type="RatingSettings", object_id=str(policy.pk),
            payload={"enabled": policy.enabled},
        )
        return policy
