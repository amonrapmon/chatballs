"""Capture and enqueue atomically with a real completion journal fact."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.domain_events import operation_key
from chatballs.events.services import DomainEvent, enqueue_event
from chatballs.i18n import t
from chatballs.tenancy.context import TenantActorKind, TenantContext

from .access import require_quality_conversation
from .criteria import require_management
from .jobs import request_quality_job
from .models import QualitySettings

QUALITY_REQUESTED = "conversation.quality_requested"


class MissingCompletionHistory(ValidationError):
    default_code = "missing_history"


def enqueue_job(context, job):
    enqueue_event(DomainEvent(
        aggregate_type="QualityJob", aggregate_id=str(job.pk), event_type=QUALITY_REQUESTED,
        payload={"job_id": job.pk}, tenant_context=TenantContext.for_resource(
            context.organization, actor_kind=TenantActorKind.SYSTEM,
        ),
    ))


@transaction.atomic
def schedule_completion(conversation, event):
    if not QualitySettings.objects.filter(organization_id=conversation.organization_id, enabled=True).exists():
        return None
    context = TenantContext.for_resource(conversation.organization, actor_kind=TenantActorKind.SYSTEM)
    job = request_quality_job(
        context=context, conversation_id=conversation.pk, completion_event_id=event.operation_id,
        completed_at=event.occurred_at, operation_id=operation_key("quality-close", event.operation_id),
    )
    enqueue_job(context, job)
    return job


@transaction.atomic
def launch_quality(*, context, conversation_id, operation_id, repeat=False):
    require_management(context)
    conversation = require_quality_conversation(context, conversation_id)
    event = ConversationEvent.objects.filter(
        organization_id=context.organization_id, conversation_id=conversation.pk, event_type="CLOSED",
    ).order_by("-sequence").first()
    if event is None:
        raise MissingCompletionHistory(t("quality.history_missing"))
    job = request_quality_job(
        context=context, conversation_id=conversation.pk, completion_event_id=event.operation_id,
        completed_at=event.occurred_at, operation_id=operation_id, repeat=repeat,
    )
    enqueue_job(context, job)
    return job
