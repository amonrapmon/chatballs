"""Display metadata belongs to protected history, not the replay result."""

from chatballs.conversations.transfer_transition import transfer_payload
from chatballs.identity.avatars import user_avatar_url_in
from chatballs.i18n import t


def transfer_history_payload(row):
    def person(user):
        return {
            "id": user.pk, "name": user.full_name or user.email,
            "avatarUrl": user_avatar_url_in(user, row.organization_id),
        } if user else None

    payload = transfer_payload(row)
    return {
        **payload,
        "initiatedBy": person(row.initiated_by),
        "previousOperator": person(row.previous_operator),
        "newOperator": person(row.new_operator),
        "conversation": {
            "contactName": getattr(row.conversation.contact, "name", "") or t("conversations.guest"),
            "provider": getattr(row.conversation.connection, "provider", ""),
        },
        "reason": {
            **payload["reason"],
            "isActive": row.reason.is_active, "currentName": row.reason.name,
        },
    }
