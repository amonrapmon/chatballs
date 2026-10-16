"""Current authorization bounds historical filters and all direct identifiers."""

from django.db.models import Q
from rest_framework.exceptions import NotFound

from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.support_access import report_scope
from chatballs.i18n import t

from .access import quality_scope
from .models import QualityJob


def quality_jobs(context):
    scope = quality_scope(context)
    return QualityJob.objects.filter(
        organization_id=context.organization_id, conversation_id__in=scope.values("pk"),
    ).select_related("criteria_version", "conversation__organization", "result").order_by("-completed_at", "-revision", "-pk")


def job_for_context(context, job_id):
    job = quality_jobs(context).filter(pk=job_id).first()
    if job is None:
        raise NotFound(t("quality.not_found"))
    return job


def report_jobs(context, filters):
    jobs = quality_jobs(context)
    # Reuse validation of dimensions against the current managed area.
    report_scope(context, filters)
    completions = ConversationEvent.objects.filter(
        organization_id=context.organization_id, event_type="CLOSED",
        conversation_id__in=quality_scope(context).values("pk"),
    )
    if filters.group is not None:
        completions = completions.filter(group_id=filters.group)
    if filters.employee is not None:
        completions = completions.filter(Q(responsible_id=filters.employee) | Q(initiated_by_id=filters.employee))
    if filters.connection is not None:
        completions = completions.filter(connection_id=filters.connection)
    if filters.transport is not None:
        completions = completions.filter(transport=filters.transport)
    jobs = jobs.filter(completed_at__gte=filters.start, completed_at__lt=filters.end)
    if any(value is not None for value in (filters.group, filters.employee, filters.connection, filters.transport)):
        jobs = jobs.filter(completion_event_id__in=completions.values("operation_id"))
    return jobs
