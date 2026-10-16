"""Protected card status and staff details in the current management scope."""

from chatballs.conversations.management_scope import management_scope
from chatballs.identity.avatars import user_avatar_url_in
from chatballs.ratings.models import RatingRequest, RatingSettings
from chatballs.ratings.results import conversation_results, protected_payload


def conversation_card(context, conversation_id):
    # Authorize even an empty card before reading request/settings metadata.
    rows = list(conversation_results(context, conversation_id))
    ids = {user_id for row in rows for user_id in row.request.responder_ids}
    members = management_scope(context, forbidden_key="ratings.forbidden").members().filter(user_id__in=ids)
    users = [member.user for member in members]
    staff = {user.pk: {"id": user.pk, "name": user.full_name,
                       "avatarUrl": user_avatar_url_in(user, context.organization_id)} for user in users}
    results = [{**protected_payload(row, permitted_staff_ids=staff), "responders": [staff[user_id] for user_id in row.request.responder_ids
                                                       if user_id in staff]} for row in rows]
    request = RatingRequest.objects.filter(
        organization_id=context.organization_id, conversation_id=conversation_id,
    ).order_by("-completion__occurred_at", "-pk").first()
    enabled = RatingSettings.objects.filter(organization_id=context.organization_id, enabled=True).exists()
    return {"results": results, "request": {"sentAt": request.sent_at.isoformat() if request.sent_at else None}
            if request else None, "enabled": enabled}
