"""Check the persisted turn generation before each provider/tool request."""

from chatballs.ai.execution_policy import execution_guard
from chatballs.ai.provider.base import ProviderError
from chatballs.conversations.ai_turn_completion import refresh_turn_control
from chatballs.tenancy.database import tenant_atomic


def guarded_call(turn, context, function, *args, **kwargs):
    def current():
        with tenant_atomic(context):
            return refresh_turn_control(turn, context)

    try:
        with execution_guard(current):
            return function(*args, **kwargs)
    except ProviderError:
        # A cancelled turn has no customer-visible failure or delivery.
        if not current():
            return None
        raise


def cancel_pending_replies(conversation):
    from chatballs.conversations.models import AiTurnState, Message

    Message.objects.filter(conversation=conversation, ai_turn_state__in=["PENDING", "RUNNING"]).update(
        ai_turn_state=AiTurnState.DONE,
    )
    for message in Message.objects.filter(conversation=conversation, ai_reply_to__isnull=False):
        if not message.ai_delivery.get("sent"):
            message.ai_delivery = {**message.ai_delivery, "cancelled": True}
            message.save(update_fields=["ai_delivery"])
