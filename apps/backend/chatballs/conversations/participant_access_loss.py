"""A former participant receives only their own access-ending fact, never history."""

from chatballs.conversations.participant_models import ConversationParticipant
from chatballs.i18n import t
from chatballs.conversations.supervision_access_loss import supervision_access_loss


def access_loss_payload(context, conversation_id):
    payload = {"detail": t("conversations.not_found")}
    row = ConversationParticipant.objects.filter(
        organization_id=context.organization_id, conversation_id=conversation_id,
        membership_id=context.membership_id, left_at__isnull=False,
    ).select_related("left_by__user").order_by("-left_at", "-id").first()
    if row is not None and row.left_by is not None:
        payload["participationEndedBy"] = row.left_by.user.full_name or row.left_by.user.email
    loss = supervision_access_loss(context, conversation_id)
    if loss is not None:
        payload["supervisionRevoked"] = loss
    return payload
