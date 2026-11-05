from chatballs.conversations.models import Conversation, LifecycleState
from chatballs.i18n import t


class ClaimError(Exception):

    pass

def _require_open(conversation: Conversation) -> None:

    if conversation.lifecycle != LifecycleState.OPEN:

        raise ClaimError(t("conversations.closed"))

def operator_label(operator) -> str:

    return getattr(operator, "full_name", "") or operator.email
