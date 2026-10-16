"""Finite process-safety budgets shared by save, preview and runtime."""

import json

from .errors import TemplateError

CONFIG_BYTES = 150_000
SOURCE_BYTES = 24_000
SCHEMA_BYTES = 16_000
DATA_BYTES = 48_000
RESULT_BYTES = 128_000
MAX_TEMPLATES = 8
MAX_DEPTH = 8
MAX_NODES = 4096
MAX_FIELDS = 128
MAX_LIST = 100
MAX_OPERATIONS = 20_000


def bounded_json(value, maximum, *, origin="configuration", tab="schema", path=""):
    # Inspect before serialization/recursive validators, including direct Python
    # callers. JSON coming from HTTP has a separate byte limit before parsing.
    pending = [(value, 0)]
    count = 0
    characters = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if isinstance(item, str):
            characters += len(item)
        elif isinstance(item, dict):
            characters += sum(len(key) for key in item if isinstance(key, str))
        if characters > maximum:
            raise TemplateError("limit", origin=origin, tab=tab, path=path)
        if depth > MAX_DEPTH * 3 or count > MAX_NODES:
            raise TemplateError("limit", origin=origin, tab=tab, path=path)
        if isinstance(item, dict | list) and len(item) + len(pending) + count > MAX_NODES:
            raise TemplateError("limit", origin=origin, tab=tab, path=path)
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    try:
        size = len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise TemplateError("invalid_value", origin=origin, tab=tab, path=path) from None
    if size > maximum:
        raise TemplateError("limit", origin=origin, tab=tab, path=path)


def source(value, *, tab, path="", maximum=SOURCE_BYTES):
    if not isinstance(value, str) or "\0" in value:
        raise TemplateError("invalid_value", tab=tab, path=path)
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise TemplateError("invalid_value", tab=tab, path=path) from None
    if size > maximum:
        raise TemplateError("limit", tab=tab, path=path)
    return value
