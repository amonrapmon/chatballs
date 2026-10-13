"""Service times use exactly the support report's reducers and coverage rules."""

from datetime import timedelta

from chatballs.conversations.domain_event_models import ConversationEvent, ConversationEventHistoryStart
from chatballs.conversations.history_selectors import customer_visible_messages
from chatballs.conversations.models import Message
from chatballs.conversations.support_filters import ReportFilters
from chatballs.conversations.support_metrics import Metrics
from chatballs.conversations.support_timeline import conversation_observations


def temporal_facts(job):
    conversation = job.conversation
    boundary = ConversationEventHistoryStart.objects.filter(pk=1).first()
    available = max(boundary.available_from, boundary.sources_available_from) if boundary else None
    events = list(ConversationEvent.objects.filter(
        organization_id=job.organization_id, conversation_id=job.conversation_id,
        occurred_at__lte=job.completed_at,
    ).order_by("sequence"))
    completion = next((e for e in events if str(e.operation_id) == str(job.completion_event_id)
                       and e.event_type == "CLOSED" and e.occurred_at == job.completed_at), None)
    complete = available is not None and conversation.created_at >= available and completion is not None
    # Reducers have an exclusive upper bound. One microsecond includes the
    # completion fact, then CLOSED ends all intervals at its real timestamp.
    upper = job.completed_at + timedelta(microseconds=1)
    filters = ReportFilters(conversation.created_at, upper, "UTC")
    incoming = customer_visible_messages(Message.objects.filter(
        organization_id=job.organization_id, conversation_id=job.conversation_id,
        author_type="CONTACT", created_at__lte=job.completed_at,
    )).only("pk", "created_at")
    metrics = Metrics()
    for observation in conversation_observations(events, incoming, upper):
        metrics.add(observation, job.conversation_id, filters)
    return {"state": "available" if complete else "missing_history", "unit": "seconds",
            "availableFrom": available.isoformat() if available else None,
            "metrics": metrics.payload(complete)}
