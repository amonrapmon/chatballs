"""История и realtime для фактических изменений данных сайта."""

from functools import partial

from django.db import transaction

from chatballs.conversations.models import (
    Conversation,
    LifecycleState,
    Message,
    MessageAuthor,
    SystemEvent,
)
from chatballs.conversations.realtime import notify_conversation_changed
from chatballs.conversations.site_fields import field_display


def _event_value(definition: dict, value: object) -> object:
    if value is not None and definition["type"] == "enum":
        return field_display(definition, value)
    return value


def record_site_field_changes(session, changes: list[tuple[dict, object, object]]) -> None:
    if not changes:
        return
    conversations = Conversation.objects.filter(
        organization_id=session.organization_id, contact_id=session.identity.contact_id,
        lifecycle=LifecycleState.OPEN,
    )
    for conversation in conversations:
        for definition, old, new in changes:
            if definition["type"] not in {"enum", "boolean"}:
                continue
            # Подписи enum — исторический снимок; boolean и пустое значение
            # остаются кодами, чтобы переводиться на языке читателя.
            Message.objects.create(
                organization_id=session.organization_id, conversation=conversation,
                author_type=MessageAuthor.SYSTEM, system_event=SystemEvent.SITE_FIELDS_UPDATED,
                system_params={"label": definition.get("label", definition.get("key", "")),
                               "old": _event_value(definition, old), "new": _event_value(definition, new), "fieldType": definition["type"]},
            )
        transaction.on_commit(partial(
            notify_conversation_changed, conversation.id, organization_id=session.organization_id,
        ))
