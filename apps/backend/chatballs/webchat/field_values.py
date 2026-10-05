"""Проверка значения поля без записи в контакт или базу."""

import math
from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email

from chatballs.webchat.services import normalize_phone

MAX_STRING_LENGTH = 500
BUILTIN_TYPES = {"name": "string", "email": "email", "phone": "phone"}


def validate_field_value(value: object, definition: dict) -> object:
    if value is None:
        return None
    field_type = definition["type"]
    if field_type == "boolean":
        if type(value) is bool:
            return value
        raise ValueError("type")
    if field_type == "number":
        if type(value) is int and value.bit_length() <= 1024:
            return value
        if type(value) is float and math.isfinite(value):
            return value
        raise ValueError("type")
    if not isinstance(value, str):
        raise ValueError("type")
    if len(value) > MAX_STRING_LENGTH:
        raise ValueError("length")
    if field_type == "datetime":
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("format") from exc
    elif field_type == "email":
        try:
            validate_email(value)
        except ValidationError as exc:
            raise ValueError("format") from exc
    elif field_type == "phone":
        phone = normalize_phone(value)
        if not phone:
            raise ValueError("format")
        return phone
    elif field_type == "url":
        try:
            URLValidator(schemes=["http", "https"])(value)
        except ValidationError as exc:
            raise ValueError("format") from exc
    elif field_type == "enum":
        if value not in {option["value"] for option in definition.get("options", [])}:
            raise ValueError("option")
    return value
