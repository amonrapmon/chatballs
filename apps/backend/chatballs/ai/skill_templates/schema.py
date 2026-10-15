"""Typed nested schemas and a separate data-validation boundary."""

import math
import re

from .errors import TemplateError
from .limits import DATA_BYTES, MAX_DEPTH, MAX_FIELDS, MAX_LIST, SCHEMA_BYTES, bounded_json

NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
TYPES = {"string", "number", "boolean", "object", "list"}


def validate_schema(schema):
    bounded_json(schema, SCHEMA_BYTES)
    fields = 0

    def visit(node, path, depth):
        nonlocal fields
        fields += 1
        if fields > MAX_FIELDS or depth > MAX_DEPTH:
            raise TemplateError("limit", path=path)
        if not isinstance(node, dict) or not isinstance(node.get("type"), str) or node["type"] not in TYPES:
            raise TemplateError("invalid_schema", path=path)
        kind = node["type"]
        allowed = {"type", "required", "description"}
        allowed |= {"properties"} if kind == "object" else {"items"} if kind == "list" else set()
        if set(node) - allowed or type(node.get("required", False)) is not bool:
            raise TemplateError("invalid_schema", path=path)
        description = node.get("description", "")
        if not isinstance(description, str) or len(description) > 500 or "\0" in description:
            raise TemplateError("invalid_schema", path=path)
        if kind == "object":
            props = node.get("properties")
            if not isinstance(props, dict):
                raise TemplateError("invalid_schema", path=path)
            for key, child in props.items():
                if not isinstance(key, str) or not NAME.fullmatch(key):
                    raise TemplateError("invalid_schema", path=path)
                visit(child, f"{path}.{key}".strip("."), depth + 1)
        elif kind == "list":
            visit(node.get("items"), path + "[]", depth + 1)

    visit(schema, "", 0)
    if schema["type"] != "object":
        raise TemplateError("invalid_schema")
    return schema


def field(schema, path):
    if path == "this" and schema["type"] != "object":
        return schema
    node = schema
    for part in path.split("."):
        if not NAME.fullmatch(part) or node["type"] != "object" or part not in node["properties"]:
            return None
        node = node["properties"][part]
    return node


def validate_data(schema, data, *, origin="data"):
    bounded_json(data, DATA_BYTES, origin=origin, tab="example")

    def fail(code, path):
        raise TemplateError(code, origin=origin, tab="example", path=path)

    def visit(node, value, path, depth=0):
        if depth > MAX_DEPTH:
            fail("limit", path)
        if value is None:
            if node.get("required"):
                fail("required", path)
            return
        kind = node["type"]
        valid = {"string": isinstance(value, str), "number": type(value) in (int, float),
                 "boolean": type(value) is bool, "object": isinstance(value, dict),
                 "list": isinstance(value, list)}[kind]
        if not valid:
            fail("type", path)
        if kind == "number" and (abs(value) > 10**15 or not math.isfinite(value)):
            fail("invalid_value", path)
        if kind == "string" and node.get("required") and not value.strip():
            fail("required", path)
        if kind == "string" and ("\0" in value or len(value) > 8000):
            fail("limit", path)
        if kind == "object":
            props = node["properties"]
            if set(value) - set(props):
                fail("unknown_field", path)
            for key, child in props.items():
                child_path = f"{path}.{key}".strip(".")
                if key not in value and child.get("required"):
                    fail("required", child_path)
                visit(child, value.get(key), child_path, depth + 1)
        elif kind == "list":
            if len(value) > MAX_LIST:
                fail("limit", path)
            for index, child in enumerate(value):
                visit(node["items"], child, f"{path}[{index}]", depth + 1)

    if not isinstance(data, dict):
        fail("type", "")
    visit(schema, data, "")
