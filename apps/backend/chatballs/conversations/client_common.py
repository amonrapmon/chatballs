from chatballs.conversations.models import ControlMode, Conversation, LifecycleState

# Короткие коды для UI (совпадают с фронтовыми справочниками).
PROVIDER_CODE = {
    "MAX": "MAX",
    "TELEGRAM": "TG",
    "VK": "VK",
    "WEB": "WEB",
    "EMAIL": "EMAIL",
}


def _actor_name(user) -> str:
    return (user.full_name or user.email) if user is not None else ""


def _mode(latest: Conversation) -> str:
    if latest.lifecycle != LifecycleState.OPEN:
        return "closed"
    if latest.control_mode == ControlMode.HUMAN:
        return "operator"
    if latest.control_mode == ControlMode.AI:
        return "ai"
    return "wait"
