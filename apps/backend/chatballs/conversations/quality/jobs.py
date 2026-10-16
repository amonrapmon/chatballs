from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from chatballs.conversations.models import Conversation, LifecycleState
from chatballs.i18n import t
from chatballs.identity.models import Organization
from chatballs.tenancy.context import TenantActorKind

from .criteria import require_management
from .history import public_history_snapshot
from .models import QualityJob, QualityJobOperation, QualityJobState, QualityResult, QualitySettings


def operation_uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError(t("quality.operation_invalid")) from error


@transaction.atomic
def request_quality_job(*, context, conversation_id, completion_event_id, completed_at,
                        operation_id, repeat=False):
    """Persistence entry point for B18.2's completion journal integration.

    Explicit retries need a new operation ID. Redelivery with the same ID
    returns the original job, even after criteria or public history changes.
    """
    if context.actor_kind != TenantActorKind.SYSTEM:
        require_management(context)
    completion_event_id, operation_id = map(operation_uuid, (completion_event_id, operation_id))
    conversation = Conversation.objects.select_for_update().filter(
        pk=conversation_id, organization_id=context.organization_id,
    ).first()
    if conversation is None:
        raise NotFound(t("quality.not_found"))
    # Closure already holds the conversation lock. Keep that order here too;
    # the org lock serializes operation IDs even across different dialogs.
    Organization.objects.select_for_update().get(pk=context.organization_id)
    jobs = QualityJob.objects.filter(organization_id=context.organization_id)
    operation = QualityJobOperation.objects.select_related("job").filter(
        organization_id=context.organization_id, operation_id=operation_id,
    ).first()
    existing = operation.job if operation else None
    if existing:
        if (existing.conversation_id != conversation_id or existing.completion_event_id != completion_event_id
                or existing.completed_at != completed_at):
            raise ValidationError(t("quality.operation_conflict"))
        return existing
    if conversation.lifecycle != LifecycleState.CLOSED:
        raise ValidationError(t("quality.closed_required"))
    if (not isinstance(completed_at, datetime)
            or timezone.is_naive(completed_at) or completed_at > timezone.now()
            or completed_at < conversation.created_at or type(repeat) is not bool):
        raise ValidationError(t("quality.completion_invalid"))
    settings = QualitySettings.objects.filter(organization_id=context.organization_id).first()
    if settings is None or not settings.enabled:
        raise ValidationError(t("quality.disabled"))
    event_jobs = jobs.filter(conversation=conversation, completion_event_id=completion_event_id)
    if event_jobs.exclude(completed_at=completed_at).exists():
        raise ValidationError(t("quality.operation_conflict"))
    snapshot, history_revision = public_history_snapshot(conversation, completed_at)
    if not repeat:
        existing = event_jobs.filter(criteria_version=settings.current_version, history_revision=history_revision).first()
        if existing:
            QualityJobOperation.objects.create(
                organization_id=context.organization_id, operation_id=operation_id, job=existing,
            )
            return existing
    revision = (event_jobs.aggregate(latest=Max("revision"))["latest"] or 0) + 1
    job = QualityJob.objects.create(
        organization_id=context.organization_id, conversation=conversation,
        completion_event_id=completion_event_id, completed_at=completed_at,
        operation_id=operation_id, criteria_version=settings.current_version,
        history_snapshot=snapshot, history_revision=history_revision, revision=revision,
    )
    QualityJobOperation.objects.create(
        organization_id=context.organization_id, operation_id=operation_id, job=job,
    )
    return job


def locked_job(context, job_id):
    # Worker contexts carry an organization resolved from their queue entry.
    if context.actor_kind != TenantActorKind.SYSTEM:
        require_management(context)
    job = QualityJob.objects.select_for_update().filter(
        pk=job_id, organization_id=context.organization_id,
    ).first()
    if job is None:
        raise NotFound(t("quality.not_found"))
    return job


@transaction.atomic
def start_quality_job(*, context, job_id):
    job = locked_job(context, job_id)
    if job.state != QualityJobState.WAITING:
        return False
    job.state = QualityJobState.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["state", "started_at"])
    return True


@transaction.atomic
def finish_quality_job(*, context, job_id, validated_result=None, error_code=""):
    """Persist trusted worker output; parsing and evidence checks live in validation."""
    job = locked_job(context, job_id)
    if job.state in (QualityJobState.SUCCEEDED, QualityJobState.FAILED):
        return job
    if job.state != QualityJobState.RUNNING:
        raise ValidationError(t("quality.state_conflict"))
    if validated_result is not None:
        if not isinstance(validated_result, dict) or not validated_result or error_code:
            raise ValidationError(t("quality.result_invalid"))
        QualityResult.objects.create(organization_id=context.organization_id, job=job, data=validated_result)
        job.state = QualityJobState.SUCCEEDED
    else:
        if not isinstance(error_code, str) or not error_code.strip() or len(error_code) > 64:
            raise ValidationError(t("quality.result_invalid"))
        job.state = QualityJobState.FAILED
        job.error_code = error_code
    job.finished_at = timezone.now()
    job.save(update_fields=["state", "error_code", "finished_at"])
    return job
