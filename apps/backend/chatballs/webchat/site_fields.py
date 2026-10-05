"""Проверка и сохранение недоверенных значений, присланных сайтом."""

import logging

from django.db import transaction

from chatballs.conversations.models import Contact, ContactFieldValue
from chatballs.webchat.field_schema import RESERVED_KEYS
from chatballs.webchat.field_values import BUILTIN_TYPES, validate_field_value
from chatballs.webchat.site_field_events import record_site_field_changes

logger = logging.getLogger(__name__)


def _schema(integration) -> dict[str, dict]:
    raw = integration.config.get("fields", [])
    fields = {item["key"]: item for item in raw if isinstance(item, dict) and item.get("key")}
    return {**{key: {"type": kind} for key, kind in BUILTIN_TYPES.items()}, **fields}


def _apply_builtin(contact: Contact, key: str, value: object, previous: ContactFieldValue | None, session) -> bool:
    current = getattr(contact, key)
    old_site_value = previous.value if previous else None
    guest_name = key == "name" and current == session.identity.display_name and session.identity.external_user_id[:6] in current
    if current and not guest_name and (previous is None or current != old_site_value):
        return False
    if value is not None and len(value) > Contact._meta.get_field(key).max_length:
        raise ValueError("length")
    setattr(contact, key, value or "")
    contact.save(update_fields=[key])
    return True


@transaction.atomic
def save_site_fields(session, fields: object) -> None:
    """Частичное обновление; плохие ключи/типы не прерывают приём."""
    if not isinstance(fields, dict):
        logger.warning("webchat fields ignored: invalid payload")
        return
    contact = Contact.objects.select_for_update().get(
        id=session.identity.contact_id, organization_id=session.organization_id
    )
    schema = _schema(session.connection)
    changes = []
    for key, raw_value in fields.items():
        definition = schema.get(key) if isinstance(key, str) else None
        if definition is None:
            logger.warning("webchat field ignored: unknown key")
            continue
        try:
            value = validate_field_value(raw_value, definition)
            previous = ContactFieldValue.objects.filter(
                contact=contact, integration=session.connection, key=key
            ).first()
            builtin_before = getattr(contact, key) if key in RESERVED_KEYS else None
            if key in RESERVED_KEYS and not _apply_builtin(contact, key, value, previous, session):
                continue
        except ValueError as exc:
            logger.warning("webchat field ignored: %s", exc)
            continue
        old_value = previous.value if previous else None
        builtin_changed = key in RESERVED_KEYS and builtin_before != getattr(contact, key)
        if old_value == value and not builtin_changed:
            continue
        if value is None:
            if previous:
                previous.delete()
        elif previous:
            previous.value = value
            previous.save(update_fields=["value", "updated_at"])
        else:
            ContactFieldValue.objects.create(
                organization_id=session.organization_id,
                contact=contact,
                integration=session.connection,
                key=key,
                value=value,
            )
        changes.append(({"key": key, **definition}, old_value, value))
    record_site_field_changes(session, changes)
