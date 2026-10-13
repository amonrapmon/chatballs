"""Read-only activity display; access is checked against the current conversation."""

from rest_framework import serializers
from rest_framework.response import Response

from chatballs.api.pagination import paginate
from chatballs.conversations.activity_history import history_index, history_records, history_sources
from chatballs.conversations.models import Conversation
from chatballs.conversations.transfer_display import transfer_history_payload
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t


class HistoryInput(serializers.Serializer):
    kind = serializers.ChoiceField(choices=("all", "transfers", "participants"), default="all")


def person(member):
    user = member.user if member else None
    return {"id": user.pk, "name": user.full_name or user.email} if user else None


def activity_payload(item, records):
    kind = item["history_kind"]
    row = records[kind][item["id"]]
    payload = {
        "id": f"{kind}:{row.pk}", "kind": kind, "occurredAt": item["history_time"].isoformat(),
        "actor": None, "recipient": None, "reason": None, "comment": "",
    }
    if kind == "TRANSFER":
        transfer = transfer_history_payload(row)
        payload.update(actor=transfer["initiatedBy"], recipient=transfer["newOperator"],
                       reason=transfer["reason"], comment=transfer["comment"])
    elif kind in ("JOIN", "LEAVE"):
        payload.update(
            actor=person(row.joined_by if kind == "JOIN" else row.left_by), recipient=person(row.membership),
            reason={"name": row.join_reason if kind == "JOIN" else row.leave_reason},
        )
    else:
        payload["actor"] = {"id": row.author_user_id, "name": row.system_params.get("operator", "")}
    return payload


class ConversationActivityView(ConversationViewBase):
    def get(self, request, conversation_id):
        data = HistoryInput(data=request.query_params)
        data.is_valid(raise_exception=True)
        try:
            conversation = self._conversation(request, conversation_id)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        sources = history_sources(conversation)
        page = paginate(history_index(sources, data.validated_data["kind"]), request.query_params)
        index = list(page.items)
        records = history_records(sources, index)
        return Response({
            "items": [activity_payload(item, records) for item in index],
            "page": page.page, "pageSize": page.page_size, "total": page.total, "pageCount": page.page_count,
        })
