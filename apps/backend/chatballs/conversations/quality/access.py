"""Quality management grants never follow ordinary operator visibility."""

from rest_framework.exceptions import NotFound, PermissionDenied

from chatballs.conversations.models import Conversation
from chatballs.i18n import t
from chatballs.identity.models import EmployeeRole
from chatballs.identity.work_status_services import own_membership


def quality_scope(context):
    actor = own_membership(context=context)
    conversations = Conversation.objects.filter(organization_id=context.organization_id)
    if actor.role == EmployeeRole.SUPERVISOR:
        conversations = conversations.filter(group_id__in=actor.supervision_links.values("group_id"))
    elif actor.role not in {EmployeeRole.OWNER, EmployeeRole.ADMIN}:
        raise PermissionDenied(t("quality.forbidden"))
    return conversations


def require_quality_conversation(context, conversation_id):
    conversation = quality_scope(context).filter(pk=conversation_id).first()
    if conversation is None:
        raise NotFound(t("quality.not_found"))
    return conversation
