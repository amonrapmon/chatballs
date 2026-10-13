"""Current reply permission shared by text, contact requests and media uploads."""

from chatballs.conversations.access import (
    has_active_participation,
    has_independent_work_access,
    require_conversation_action,
)
from chatballs.conversations.models import ControlMode, Conversation
from chatballs.i18n import t
from chatballs.identity.policy import can_administer_access


def lock_for_reply(*, context, conversation_id):
    # Shares the composition lock with participant removal: an old HTTP object
    # never keeps a participation grant alive beyond the removal transaction.
    conversation = Conversation.objects.select_for_update().get(
        pk=conversation_id, organization_id=context.organization_id,
    )
    require_conversation_action(context, conversation, "conversations.operate")
    return conversation


def require_human_reply(*, context, conversation, allow_unclaimed=False):
    from chatballs.conversations.services import ClaimError, _require_open

    require_conversation_action(context, conversation, "conversations.operate")
    _require_open(conversation)
    manager = can_administer_access(context.membership)
    if allow_unclaimed and conversation.control_mode != ControlMode.HUMAN and (
        manager or has_independent_work_access(context.membership, conversation)
    ):
        return
    if conversation.control_mode != ControlMode.HUMAN or not (
        conversation.assigned_operator_id == context.actor_user.pk
        or manager
        or has_active_participation(context.membership, conversation)
    ):
        raise ClaimError(t("conversations.handled_by_other"))
