from django.db import transaction
from django.db.models import Max
from rest_framework.exceptions import NotFound, ValidationError

from chatballs.i18n import t

from .criteria import require_management
from .models import QualityCorrection, QualityResult


@transaction.atomic
def append_quality_correction(*, context, result_id, expected_revision, criterion_code, value, reason):
    """Append-only foundation. Supervisor policy and public API belong to B18.4."""
    require_management(context)
    result = QualityResult.objects.select_for_update().filter(
        pk=result_id, organization_id=context.organization_id,
    ).first()
    if result is None:
        raise NotFound(t("quality.not_found"))
    latest = result.corrections.aggregate(latest=Max("revision"))["latest"] or 0
    if type(expected_revision) is not int or expected_revision != latest:
        raise ValidationError(t("quality.correction_conflict"))
    criteria = {item["code"]: item for item in result.job.criteria_version.criteria}
    criterion = criteria.get(criterion_code) if isinstance(criterion_code, str) else None
    if criterion is None or not any(type(value) is type(item) and value == item for item in criterion["scale"]):
        raise ValidationError(t("quality.correction_invalid"))
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError(t("quality.reason_required"))
    return QualityCorrection.objects.create(
        organization_id=context.organization_id, result=result, revision=latest + 1,
        criterion_code=criterion_code, value=value, author=context.membership, reason=reason.strip(),
    )
