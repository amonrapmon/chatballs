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
    if not isinstance(raw, dict) or set(raw) != required:
        raise TemplateError("invalid_schema")
    try:
        identifier = str(uuid.UUID(raw["id"]))
    except (ValueError, TypeError, AttributeError):
        raise TemplateError("invalid_value", path="id") from None
    for key, limit in (("name", 60), ("purpose", 500)):
        if not source(raw[key], tab="schema", path=key, maximum=limit).strip():
            raise TemplateError("required", path=key)
    schema = validate_schema(raw["schema"])
    html = compile_source(raw["html"], schema, tab="html")
    text = compile_source(raw["text"], schema, tab="text")
    if not raw["text"].strip() or not raw["html"].strip():
        raise TemplateError("required", tab="text" if not raw["text"].strip() else "html")
    clean_html(skeleton(html), static=True)
    validate_structure(raw["html"], html)
    css = clean_css(raw["css"])
    # Examples are editor data, never runtime arguments. A temporary incomplete
    # example does not invalidate a correct configuration at save time.
    if not isinstance(raw["examples"], list) or len(raw["examples"]) > 8:
        raise TemplateError("limit", tab="example", path="examples")
    bounded_json(raw["examples"], 48_000, tab="example", path="examples")
    return CompiledTemplate({**raw, "id": identifier}, html, text, css)


def validate_templates(raw):
    if not isinstance(raw, list) or len(raw) > MAX_TEMPLATES:
        raise TemplateError("limit", path="templates")
    result = []
    ids = set()
    for index, item in enumerate(raw):
        try:
            compiled = compile_template(item)
            if compiled.configuration["id"] in ids:
                raise TemplateError("invalid_value", path="id")
            ids.add(compiled.configuration["id"])
            result.append(compiled.configuration)
        except TemplateError as error:
            detail = error.detail["errors"][0]
            detail["path"] = f"templates[{index}]" + (f".{detail['path']}" if detail["path"] else "")
            raise
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
