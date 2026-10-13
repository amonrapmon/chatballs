"""Current management scope; one result row, grouped by exact scale snapshot."""

import hashlib
import json

from rest_framework.exceptions import NotFound, PermissionDenied

from chatballs.i18n import t
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.identity.policy import MANAGEMENT_ROLES
from chatballs.ratings.models import CustomerRating
from chatballs.ratings.public_service import result_payload


def management_conversations(context):
    from chatballs.conversations.models import Conversation

    actor = context.actor_user
    membership = OrganizationMembership.objects.filter(
        pk=context.membership_id, organization_id=context.organization_id,
        user_id=actor.pk if actor else None, blocked_at__isnull=True, user__is_active=True,
    ).first()
    if membership is None or membership.role not in {*MANAGEMENT_ROLES, EmployeeRole.SUPERVISOR}:
        raise PermissionDenied(t("ratings.forbidden"))
    conversations = Conversation.objects.filter(organization_id=context.organization_id)
    if membership.role == EmployeeRole.SUPERVISOR:
        conversations = conversations.filter(group_id__in=membership.supervision_links.values("group_id"))
    return conversations


def results_for_context(context):
    return CustomerRating.objects.filter(
        organization_id=context.organization_id,
        request__conversation__in=management_conversations(context),
    ).select_related("request").order_by("-received_at", "-pk")


def protected_payload(result):
    request = result.request
    return {"id": result.pk, "requestId": str(request.public_id),
            "conversationId": request.conversation_id, "completionId": request.completion_id,
            "responderIds": request.responder_ids, "scale": request.scale,
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
