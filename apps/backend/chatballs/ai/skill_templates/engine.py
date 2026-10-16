"""The only compilation/render pipeline, used by save, preview and runtime."""

import uuid
from dataclasses import dataclass

from .css_policy import clean_css
from .errors import TemplateError
from .html_policy import clean_html
from .html_structure import validate_structure
from .isolation import isolated_document
from .language import compile_source, render, skeleton
from .limits import MAX_TEMPLATES, RESULT_BYTES, bounded_json, source
from .schema import validate_data, validate_schema


@dataclass(frozen=True)
class CompiledTemplate:
    configuration: dict
    html: list
    text: list
    css: str


def compile_template(raw):
    required = {"id", "name", "purpose", "schema", "html", "css", "text", "examples"}
    if not isinstance(raw, dict) or not required <= set(raw) or set(raw) - required - {"exampleNames"}:
        raise TemplateError("invalid_schema")
    try:
        identifier = str(uuid.UUID(raw["id"]))
    except (ValueError, TypeError, AttributeError):
        raise TemplateError("invalid_value", path="id") from None
    for key, limit in (("name", 60), ("purpose", 500)):
        if not source(raw[key], tab="schema", path=key, maximum=limit).strip():
            raise TemplateError("required", path=key)
    schema = validate_schema(raw["schema"])
    errors = []
    compiled = {}
    for tab in ("html", "text", "css"):
        try:
            if tab == "css":
                compiled[tab] = clean_css(raw[tab])
                continue
            nodes = compile_source(raw[tab], schema, tab=tab)
            if not raw[tab].strip():
                raise TemplateError("required", tab=tab)
            if tab == "html":
                clean_html(skeleton(nodes), static=True)
                validate_structure(raw[tab], nodes)
            compiled[tab] = nodes
        except TemplateError as error:
            errors.extend(error.detail["errors"])
    if errors:
        raise TemplateError.combined(errors)
    # Examples are editor data, never runtime arguments. A temporary incomplete
    # example does not invalidate a correct configuration at save time.
    if not isinstance(raw["examples"], list) or len(raw["examples"]) > 8:
        raise TemplateError("limit", tab="example", path="examples")
    bounded_json(raw["examples"], 48_000, tab="example", path="examples")
    names = raw.get("exampleNames", [])
    if not isinstance(names, list) or len(names) > 8:
        raise TemplateError("limit", tab="example", path="exampleNames")
    for name in names:
        if not source(name, tab="example", path="exampleNames", maximum=240).strip() or len(name) > 60:
            raise TemplateError("invalid_value", tab="example", path="exampleNames")
    return CompiledTemplate({**raw, "id": identifier}, compiled["html"], compiled["text"], compiled["css"])


def validate_templates(raw):
    if not isinstance(raw, list) or len(raw) > MAX_TEMPLATES:
        raise TemplateError("limit", path="templates")
    result = []
    ids = set()
    errors = []
    for index, item in enumerate(raw):
        try:
            compiled = compile_template(item)
            if compiled.configuration["id"] in ids:
                raise TemplateError("invalid_value", path="id")
            ids.add(compiled.configuration["id"])
            result.append(compiled.configuration)
        except TemplateError as error:
            for detail in error.detail["errors"]:
                detail["path"] = f"templates[{index}]" + (f".{detail['path']}" if detail["path"] else "")
                errors.append(detail)
    if errors:
        raise TemplateError.combined(errors)
    return result


def render_template(template, data, *, language, origin="data"):
    compiled = compile_template(template)
    validate_data(template["schema"], data, origin=origin)
    text = render(compiled.text, data, language=language, origin=origin)
    html = clean_html(render(compiled.html, data, language=language, html=True, origin=origin), origin=origin)
    document = isolated_document(html, compiled.css)
    if len((text + html + compiled.css + document).encode("utf-8")) > RESULT_BYTES:
        raise TemplateError("limit", origin=origin)
    return {"text": text, "contentHtml": html, "presentation": {
        "formatVersion": 1, "css": compiled.css, "isolation": "sandboxed-iframe",
        "sandbox": "", "srcDoc": document,
    }}
