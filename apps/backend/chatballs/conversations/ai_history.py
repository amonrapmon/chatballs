"""Ограниченная история диалога для хода AI."""

from chatballs.conversations.models import Conversation, MessageAuthor

_ROLE = {
    MessageAuthor.CONTACT: "user",
    MessageAuthor.AI: "assistant",
    MessageAuthor.OPERATOR: "assistant",
    MessageAuthor.SYSTEM: "system",
}


def conversation_history(conversation: Conversation, limit: int) -> list[dict]:
    # С конца и с ограничением в базе: длинный диалог не поднимается в память
    # целиком ради последних сообщений. Самое новое — входящее, по которому
    # идёт ход, оно уходит модели отдельно.
    latest = conversation.messages.order_by("-created_at", "-id")[: limit + 1]
    prior = list(reversed(latest))[:-1]
    # Голосовые попадают в контекст стенограммой.
    return [
        {"role": _ROLE.get(m.author_type, "user"), "content": m.text or m.transcript}
        for m in prior
        if m.text or m.transcript
    ]
