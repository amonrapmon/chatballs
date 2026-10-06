"""Заголовки внешнего сервера: открытые — в config, секретные — в шифре.

В ``config["headers"]`` лежат имена, порядок и значения открытых заголовков;
значения секретных — в ``Integration.secret_headers`` (JSON «имя → значение»,
Fernet). Наружу секретное значение не отдаётся: его можно только заменить
(SPEC-0023 R-1). Пустое значение секретного заголовка при сохранении значит
«оставить прежнее» — как у секрета интеграции.
"""

from __future__ import annotations

import json
import re

from chatballs.integrations.external_errors import SettingsErrors
from chatballs.integrations.models import Integration

MAX_HEADERS = 10
MAX_VALUE_LENGTH = 1024
# Имя заголовка — token из RFC 9110.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$")
# Этими заголовками управляет сам клиент (``tool_client``).
RESERVED_NAMES = frozenset({"host", "content-length", "transfer-encoding", "connection"})


def stored_secret_headers(integration: Integration) -> dict[str, str]:
    if not integration.secret_headers:
        return {}
    try:
        stored = json.loads(integration.secret_headers)
    except ValueError:
        return {}
    return {str(name): str(value) for name, value in stored.items()} if isinstance(stored, dict) else {}


def dump_secret_headers(secrets: dict[str, str]) -> str:
    return json.dumps(secrets, ensure_ascii=False) if secrets else ""


def _valid_value(value: str) -> bool:
    # Перенос строки в значении — это второй заголовок, подложенный в запрос.
    if not value or len(value) > MAX_VALUE_LENGTH or not value.isprintable():
        return False
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return True


def normalize_headers(
    submitted: object, *, previous_secrets: dict[str, str], errors: SettingsErrors
) -> tuple[list[dict], dict[str, str]]:
    """Вернуть заголовки для config и значения секретных — для шифра."""
    if not isinstance(submitted, list):
        errors.add("headers", "integrations.tool_header_invalid", name="")
        return [], {}
    if len(submitted) > MAX_HEADERS:
        errors.add("headers", "integrations.tool_headers_limit", limit=MAX_HEADERS)
        return [], {}
    kept = {name.lower(): value for name, value in previous_secrets.items()}
    headers: list[dict] = []
    secrets: dict[str, str] = {}
    seen: set[str] = set()
    for raw in submitted:
        item = raw if isinstance(raw, dict) else {}
        name = str(item.get("name") or "").strip()
        if not NAME_PATTERN.match(name) or name.lower() in RESERVED_NAMES:
            errors.add("headers", "integrations.tool_header_invalid", name=name)
            continue
        if name.lower() in seen:
            errors.add("headers", "integrations.tool_header_duplicate", name=name)
            continue
        seen.add(name.lower())
        secret = bool(item.get("secret"))
        value = str(item.get("value") or "").strip()
        if not value and secret:
            value = kept.get(name.lower(), "")
        if not value:
            errors.add("headers", "integrations.tool_header_value_required", name=name)
        elif not _valid_value(value):
            errors.add("headers", "integrations.tool_header_invalid", name=name)
        elif secret:
            headers.append({"name": name, "secret": True})
            secrets[name] = value
        else:
            headers.append({"name": name, "secret": False, "value": value})
    return headers, secrets


def headers_payload(stored: object) -> list[dict]:
    """Заголовки для настроек: у секретного — только имя и признак."""
    return [
        {
            "name": header["name"],
            "secret": bool(header.get("secret")),
            "value": "" if header.get("secret") else header.get("value", ""),
        }
        for header in (stored if isinstance(stored, list) else [])
    ]


def request_headers(integration: Integration) -> dict[str, str]:
    """Заголовки для запроса к серверу — вместе с секретными значениями."""
    secrets = stored_secret_headers(integration)
    result: dict[str, str] = {}
    for header in integration.config.get("headers", []):
        value = secrets.get(header["name"], "") if header.get("secret") else header.get("value", "")
        if value:
            result[header["name"]] = value
    return result
