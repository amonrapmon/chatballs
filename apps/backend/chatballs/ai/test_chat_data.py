"""Тестовые данные проверочного чата: проверка схемы и контекст только в памяти."""

from dataclasses import dataclass, field

from rest_framework.exceptions import ValidationError

from chatballs.ai.pseudonymization import (
    KnownValue,
    Pseudonymizer,
    contact_known_values,
)
from chatballs.ai.site_context import MASKED, OPEN, _display_value
from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact
from chatballs.i18n import t
from chatballs.integrations.http_tool import ClientData
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.webchat.field_values import BUILTIN_TYPES, validate_field_value


@dataclass(frozen=True, repr=False)
class PreviewClientData:
    client: ClientData = field(repr=False)
    pseudonymizer: Pseudonymizer = field(repr=False)
    context_fields: list[tuple[str, str]] = field(repr=False)


def _invalid() -> ValidationError:
    # Не возвращаем значения, присланные клиентом, даже в ошибке.
    return ValidationError({"clientData": t("ai.test_client_data_invalid")})


def parse_test_client_data(channel: Channel, raw: object) -> PreviewClientData:
    """webFields: ID подключения → ключ поля → значение; отсутствующее — пусто.

    Разрешены лишь текущие поля веб-подключений этого агента и организации.
    Обязательность формы перед чатом здесь не применяется: неполный набор
    позволяет проверить поведение агента без привязанных значений.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, dict) or raw.keys() - {*BUILTIN_TYPES, "webFields"}:
        raise _invalid()
    builtins = {}
    for key, kind in BUILTIN_TYPES.items():
        value = raw.get(key)
        try:
            value = "" if value is None or value == "" else validate_field_value(value, {"type": kind})
        except ValueError as error:
            raise _invalid() from error
        if len(value) > Contact._meta.get_field(key).max_length:
            raise _invalid()
        builtins[key] = value
    submitted = raw.get("webFields", {})
    if not isinstance(submitted, dict):
        raise _invalid()
    connections = {
        str(item.id): item
        for item in Integration.objects.filter(
            organization_id=channel.organization_id,
            channel_id=channel.id,
            provider=IntegrationProvider.WEB,
        ).order_by("id")
    }
    if submitted.keys() - connections.keys():
        raise _invalid()
    known = contact_known_values(**builtins)
    lines = [(label, value) for key, label in (
        ("name", "Имя"), ("email", "E-mail"), ("phone", "Телефон")
    ) if (value := builtins[key])]
    web_fields: dict[int, dict[str, object]] = {}
    for connection_id, connection in connections.items():
        values = submitted.get(connection_id, {})
        definitions = sorted(connection.config.get("fields", []), key=lambda item: item.get("order", 0))
        if not isinstance(values, dict) or values.keys() - {item["key"] for item in definitions}:
            raise _invalid()
        validated = {}
        for definition in definitions:
            key = definition["key"]
            if key not in values:
                continue
            try:
                value = validate_field_value(values[key], definition)
            except ValueError as error:
                raise _invalid() from error
            if value is None:
                continue
            validated[key] = value
            display = _display_value(definition, value)
            if display.strip():
                access = definition.get("ai_access")
                if access == MASKED:
                    known.append(KnownValue(key, str(value), is_phone=definition["type"] == "phone"))
                    known.append(KnownValue(key, display, is_phone=definition["type"] == "phone"))
                if access in (MASKED, OPEN):
                    lines.append((definition["label"], display))
        web_fields[connection.id] = validated
    return PreviewClientData(
        client=ClientData(**builtins, web_fields=web_fields),
        pseudonymizer=Pseudonymizer(known),
        context_fields=lines,
    )
