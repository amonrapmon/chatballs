"""Current comment access, shared by HTTP, services and socket delivery."""

from rest_framework.exceptions import NotFound

from chatballs.conversations.models import Conversation
from chatballs.conversations.participant_models import ConversationParticipant
from chatballs.conversations.selectors import conversation_is_visible
from chatballs.i18n import t
from chatballs.identity.models import OrganizationMembership
from chatballs.identity.policy import require_capability


def current_comment_actor(*, organization_id, membership_id, user_id):
    return OrganizationMembership.objects.select_related("user").filter(
        organization_id=organization_id, pk=membership_id, user_id=user_id,
        blocked_at__isnull=True, user__is_active=True,
    ).first()


def may_access_comments(*, actor, conversation, capability="conversations.view"):
    if not require_capability(actor, capability, conversation):
        return False
    if conversation_is_visible(actor=actor, conversation=conversation):
        return True
    return ConversationParticipant.objects.active().filter(
        organization_id=conversation.organization_id,
        conversation_id=conversation.pk, membership_id=actor.pk,
    ).exists()


def comment_conversation(*, context, conversation_id, capability="conversations.view"):
    actor = current_comment_actor(
        organization_id=context.organization_id, membership_id=context.membership_id,
        user_id=getattr(context.actor_user, "pk", None),
    )
    conversation = Conversation.objects.filter(
        organization_id=context.organization_id, pk=conversation_id,
    ).first()
    if conversation is None or not may_access_comments(
        actor=actor, conversation=conversation, capability=capability,
    ):
        raise NotFound(t("conversations.not_found"))
    return conversation
