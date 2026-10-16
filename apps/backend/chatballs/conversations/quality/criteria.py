import math
import re

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from chatballs.i18n import t
from chatballs.identity.models import Organization
from chatballs.identity.policy import ResourceScope, authorize
from chatballs.identity.work_status_services import own_membership

from .models import QualityCriteriaVersion, QualitySettings


def require_management(context):
    own_membership(context=context)
    if (context.actor_user is None or context.membership is None
            or context.actor_user.pk != context.membership.user_id
            or not authorize(context.membership, "settings.manage", ResourceScope(context.organization_id))):
        raise PermissionDenied(t("quality.forbidden"))


def validate_criteria(criteria, *, allow_empty=False):
    if not isinstance(criteria, list) or (not criteria and not allow_empty):
        raise ValidationError(t("quality.criteria_required"))
    codes = set()
    for criterion in criteria:
        if (not isinstance(criterion, dict) or not {"code", "description", "scale"} <= set(criterion)
                or set(criterion) - {"code", "description", "scale", "name", "reporting"}):
            raise ValidationError(t("quality.criteria_invalid"))
        code, description, scale = (criterion[key] for key in ("code", "description", "scale"))
        if (not isinstance(code, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", code)
                or code in codes or not isinstance(description, str) or not description.strip()
                or not isinstance(scale, list) or not scale):
            raise ValidationError(t("quality.criteria_invalid"))
        for value in scale:
            if (type(value) not in (str, int, float) or (isinstance(value, str) and not value.strip())
                    or (isinstance(value, float) and not math.isfinite(value))):
                raise ValidationError(t("quality.criteria_invalid"))
        if len({(type(value), value) for value in scale}) != len(scale):
            raise ValidationError(t("quality.criteria_invalid"))
        if "name" in criterion and (not isinstance(criterion["name"], str)
                                    or not criterion["name"].strip() or len(criterion["name"]) > 200):
            raise ValidationError(t("quality.criteria_invalid"))
        if "reporting" in criterion:
            reporting = criterion["reporting"]
            if (not isinstance(reporting, dict) or set(reporting) != {"positiveValue"}
                    or len(scale) != 2 or not all(isinstance(value, str) for value in scale)
                    or reporting["positiveValue"] not in scale):
                raise ValidationError(t("quality.criteria_invalid"))
        codes.add(code)


@transaction.atomic
def configure_quality(*, context, enabled, criteria=None):
    require_management(context)
    if type(enabled) is not bool:
        raise ValidationError(t("quality.criteria_invalid"))
    # The organization row exists even before the first configuration; locking
    # it serializes initial creation, version allocation and job snapshots.
    Organization.objects.select_for_update().get(pk=context.organization_id)
    settings, _ = QualitySettings.objects.get_or_create(organization_id=context.organization_id)
    if criteria is not None:
        validate_criteria(criteria, allow_empty=not enabled)
        latest = QualityCriteriaVersion.objects.filter(organization_id=context.organization_id).order_by("-version").first()
        settings.current_version = QualityCriteriaVersion.objects.create(
            organization_id=context.organization_id, version=latest.version + 1 if latest else 1,
            criteria=criteria, created_by=context.membership,
        )
    if enabled:
        validate_criteria(settings.current_version.criteria if settings.current_version else None)
    settings.enabled = enabled
    settings.save()
    return settings
