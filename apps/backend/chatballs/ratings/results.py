"""Current management scope; one result row, grouped by exact scale snapshot."""

import hashlib
import json

from rest_framework.exceptions import NotFound

from chatballs.conversations.management_scope import management_scope
from chatballs.i18n import t
from chatballs.ratings.models import CustomerRating
from chatballs.ratings.public_service import result_payload


def management_conversations(context):
    return management_scope(context, forbidden_key="ratings.forbidden").conversations()


def results_for_context(context):
    return CustomerRating.objects.filter(
        organization_id=context.organization_id,
        request__conversation__in=management_conversations(context),
    ).select_related("request").order_by("-received_at", "-pk")


def protected_payload(result, *, permitted_staff_ids):
    request = result.request
    return {"id": result.pk, "requestId": str(request.public_id),
            "conversationId": request.conversation_id, "completionId": request.completion_id,
            "responderIds": [pk for pk in request.responder_ids if pk in permitted_staff_ids], "scale": request.scale,
            **result_payload(result)}


def scale_groups(results):
    groups = {}
    # No joins on responders: multi-staff attribution never multiplies totals.
    for result in results:
        scale = result.request.scale
        key = hashlib.sha256(json.dumps(scale, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        group = groups.setdefault(key, {"scaleId": key, "scale": scale, "count": 0, "values": {}})
        group["count"] += 1
        group["values"][result.value] = group["values"].get(result.value, 0) + 1
    return list(groups.values())


def conversation_results(context, conversation_id):
    # Apply the same management scope even to an as-yet unrated conversation.
    if not management_conversations(context).filter(pk=conversation_id).exists():
        raise NotFound(t("ratings.unavailable"))
    return results_for_context(context).filter(request__conversation_id=conversation_id)
