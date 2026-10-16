"""Bounded, globally ordered index of protected conversation activity."""

from django.db.models import CharField, F, Value

from chatballs.conversations.models import Message, SystemEvent
from chatballs.conversations.participant_models import ConversationParticipant
from chatballs.conversations.transfer_models import ConversationTransfer


def history_sources(conversation):
    scope = {"organization_id": conversation.organization_id, "conversation": conversation}
    return {
        "TRANSFER": ConversationTransfer.objects.filter(**scope).select_related(
            "reason", "initiated_by", "previous_operator", "new_operator",
            "conversation__contact", "conversation__connection",
        ),
        "JOIN": ConversationParticipant.objects.filter(**scope).select_related(
            "membership__user", "joined_by__user", "left_by__user",
        ),
        "LEAVE": ConversationParticipant.objects.filter(**scope, left_at__isnull=False).select_related(
            "membership__user", "joined_by__user", "left_by__user",
        ),
        "CLAIM": Message.objects.filter(
            **scope, system_event=SystemEvent.OPERATOR_TOOK, system_params__fromQueue=True,
        ),
    }


def history_index(sources, kind):
    fields = {"TRANSFER": "occurred_at", "JOIN": "joined_at", "LEAVE": "left_at", "CLAIM": "created_at"}
    selected = {"transfers": ("TRANSFER",), "participants": ("JOIN", "LEAVE")}.get(kind, fields)
    queries = [sources[event].order_by().annotate(
        history_time=F(fields[event]), history_kind=Value(event, output_field=CharField()),
    ).values("id", "history_time", "history_kind") for event in selected]
    return queries[0].union(*queries[1:], all=True).order_by("-history_time", "history_kind", "-id")


def history_records(sources, index):
    return {
        kind: {row.pk: row for row in source.filter(pk__in=[item["id"] for item in index if item["history_kind"] == kind])}
        for kind, source in sources.items()
    }
