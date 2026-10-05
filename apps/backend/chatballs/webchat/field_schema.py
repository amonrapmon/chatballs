"""Схема своих полей веб-подключения (SPEC-0019 R-1, R-2, R-8).

Схема живёт в ``integration.config["fields"]`` в snake_case; наружу — в
camelCase. Каждое поле получает служебный ``id``, выданный сервером: по нему
видно, что правка пришла к существующему полю, и ключ такого поля менять
нельзя — сохранённые значения и код на сайте завязаны на ключ.
"""

import re
import uuid

from django.core.exceptions import ValidationError

from chatballs.i18n import t

FIELD_TYPES = ("string", "number", "boolean", "datetime", "enum", "email", "phone", "url")
# Имя, email и телефон пишутся в сам контакт (R-10), своим полем их не завести.
RESERVED_KEYS = frozenset({"name", "email", "phone"})
MAX_FIELDS = 30
MAX_LABEL_LENGTH = 60
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


def _error(message: str, /, **params: object) -> ValidationError:
    return ValidationError({"config": t(message, **params)})


def _label(raw: object, *, key: str) -> str:
    label = str(raw or "").strip()
    if not label:
        raise _error("settings.web_field_label_required", key=key)
    if len(label) > MAX_LABEL_LENGTH:
        raise _error("settings.web_field_label_too_long", key=key, limit=MAX_LABEL_LENGTH)
    return label


def _options(raw: object, *, key: str) -> list[dict]:
    if not isinstance(raw, list):
        raise _error("settings.web_field_option_invalid", key=key)
    options: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise _error("settings.web_field_option_invalid", key=key)
        value = str(item.get("value") or "").strip()
        label = str(item.get("label") or "").strip()
        color = str(item.get("color") or "").strip()
        if not value or len(label) > MAX_LABEL_LENGTH or (color and not COLOR_PATTERN.match(color)):
            raise _error("settings.web_field_option_invalid", key=key)
        if value in seen:
            raise _error("settings.web_field_option_duplicate", key=key, value=value)
        seen.add(value)
        option = {"value": value, "label": label or value}
        if color:
            option["color"] = color
        options.append(option)
    return options


def _field(raw: object, *, previous_keys: dict[str, str]) -> dict:
    if not isinstance(raw, dict):
        raise _error("settings.web_fields_list")
    key = raw.get("key")
    if not isinstance(key, str) or not KEY_PATTERN.match(key):
        raise _error("settings.web_field_key_invalid", key=str(key or ""))
    if key in RESERVED_KEYS:
        raise _error("settings.web_field_key_reserved", key=key)
    field_id = str(raw.get("id") or "")
    if field_id in previous_keys and previous_keys[field_id] != key:
        raise _error("settings.web_field_key_immutable", key=previous_keys[field_id])
    field_type = raw.get("type")
    if field_type not in FIELD_TYPES:
        raise _error("settings.web_field_type_invalid", key=key)
    raw_options = raw.get("options")
    if field_type != "enum" and raw_options not in (None, []):
        raise _error("settings.web_field_options_only_enum", key=key)
    field = {
        # Неизвестный id — поле, удалённое в соседней вкладке, или выдумка
        # клиента: такое поле считается новым и получает свой id.
        "id": field_id if field_id in previous_keys else uuid.uuid4().hex[:12],
        "key": key,
        "label": _label(raw.get("label"), key=key),
        "type": field_type,
        "ai_visible": bool(raw.get("aiVisible", raw.get("ai_visible", False))),
    }
    if field_type == "enum":
        field["options"] = _options(raw_options or [], key=key)
    return field


def normalize_fields(submitted: object, previous: object) -> list[dict]:
    """Проверить схему из запроса и привести к виду хранения.

    Порядок задаёт ``order``, при равенстве — позиция в запросе; после
    сохранения ``order`` — это просто 0..n-1.
    """
    if not isinstance(submitted, list):
        raise _error("settings.web_fields_list")
    if len(submitted) > MAX_FIELDS:
        raise _error("settings.web_fields_limit", limit=MAX_FIELDS)
    previous_keys = {
        str(item["id"]): item["key"]
        for item in (previous if isinstance(previous, list) else [])
        if isinstance(item, dict) and item.get("id") and item.get("key")
    }
    ranked: list[tuple[float, int, dict]] = []
    seen: set[str] = set()
    for index, raw in enumerate(submitted):
        field = _field(raw, previous_keys=previous_keys)
        if field["key"] in seen:
            raise _error("settings.web_field_key_duplicate", key=field["key"])
        seen.add(field["key"])
        order = raw.get("order")
        rank = order if isinstance(order, int | float) and not isinstance(order, bool) else index
        ranked.append((rank, index, field))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [{**field, "order": position} for position, (_, _, field) in enumerate(ranked)]


def fields_payload(stored: object) -> list[dict]:
    """Схема для настроек подключения: всё, включая id и aiVisible."""
    return [
        {
            "id": field.get("id", ""),
            "key": field["key"],
            "label": field["label"],
            "type": field["type"],
            **({"options": field.get("options", [])} if field["type"] == "enum" else {}),
            "aiVisible": bool(field.get("ai_visible")),
            "order": field.get("order", position),
        }
        for position, field in enumerate(stored if isinstance(stored, list) else [])
    ]


def public_fields(stored: object) -> list[dict]:
    """Схема для виджета на сайте: без признака «Видит AI» и служебного id —
    посетителю незачем знать, что из его данных уходит модели (R-8)."""
    return [
        {key: value for key, value in field.items() if key not in ("id", "aiVisible")}
        for field in fields_payload(stored)
    ]
