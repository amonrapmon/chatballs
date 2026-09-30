"""Настройка формы перед чатом и серверная версия согласия (SPEC-0020)."""

import re

from django.core.exceptions import ValidationError

from chatballs.i18n import t
from chatballs.webchat.field_schema import RESERVED_KEYS


def pre_chat_payload(config: dict) -> dict:
    stored = config.get("preChat", {})
    return {
        "enabled": stored.get("enabled", False),
        "title": stored.get("title", ""),
        "fields": [dict(item) for item in stored.get("fields", [])],
    }


def normalize_pre_chat(config: dict, previous: dict, fields: list[dict]) -> dict:
    allowed = RESERVED_KEYS | {item["key"] for item in fields}
    removed = {item["key"] for item in previous.get("fields", [])} - allowed
    if "preChat" not in config:
        result = pre_chat_payload(previous)
        result["fields"] = [item for item in result["fields"] if item["key"] in allowed]
        return result
    raw = config["preChat"]
    if not isinstance(raw, dict):
        raise ValidationError({"config": t("settings.pre_chat_invalid")})
    enabled = raw.get("enabled", False)
    title = raw.get("title", "")
    selected = raw.get("fields", [])
    if type(enabled) is not bool or not isinstance(title, str) or not isinstance(selected, list):
        raise ValidationError({"config": t("settings.pre_chat_invalid")})
    result = []
    seen = set()
    for item in selected:
        if not isinstance(item, dict):
            raise ValidationError({"config": t("settings.pre_chat_invalid")})
        key = item.get("key")
        required = item.get("required", False)
        if not isinstance(key, str):
            raise ValidationError({"config": t("settings.pre_chat_unknown_field")})
        if type(required) is not bool or key in seen:
            raise ValidationError({"config": t("settings.pre_chat_invalid")})
        seen.add(key)
        # Полная форма настроек может прислать прежний preChat вместе с
        # удалением схемы: удалённое поле убираем и из этого списка.
        if "fields" in config and key in removed:
            continue
        if key not in allowed:
            raise ValidationError({"config": t("settings.pre_chat_unknown_field")})
        result.append({"key": key, "required": required})
    return {"enabled": enabled, "title": title.strip(), "fields": result}


def normalize_consent(config: dict, previous: dict | None) -> dict:
    stored = previous or {}
    text = str(config.get("consentText", config.get("consent_text", stored.get("consent_text", "")))).strip()
    version = str(stored.get("consent_version") or "v1")
    if previous is not None and text != stored.get("consent_text", ""):
        # Поддерживаем прежние версии вида «v1», «1», «rev-2»; для произвольной
        # старой версии начинаем числовой суффикс. Клиент версию не назначает.
        match = re.fullmatch(r"(.*?)(\d+)", version)
        version = f"{match[1]}{int(match[2]) + 1}" if match else f"{version}.1"
    return {"consent_text": text, "consent_version": version}
