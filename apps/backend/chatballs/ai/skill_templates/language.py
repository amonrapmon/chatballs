"""Only interpolation, each and if. No expressions, helpers or app objects."""

from html import escape

from chatballs.i18n.formatting import fmt

from .errors import TemplateError
from .limits import MAX_DEPTH, MAX_OPERATIONS, RESULT_BYTES, source
from .schema import field

PLACEHOLDER = "skilltemplatevalue9efc2"


def compile_source(value, schema, *, tab):
    source(value, tab=tab)
    if PLACEHOLDER in value:
        raise TemplateError("syntax", tab=tab, source=value, offset=value.index(PLACEHOLDER))
    root = []
    stack = [(None, schema, root)]
    position = 0

    def fail(code, offset):
        raise TemplateError(code, tab=tab, source=value, offset=offset)

    while position < len(value):
        start = value.find("{{", position)
        if start < 0:
            literal = value[position:]
            if "}}" in literal:
                fail("syntax", position)
            stack[-1][2].append(("literal", literal, None))
            break
        literal = value[position:start]
        if "}}" in literal:
            fail("syntax", position)
        stack[-1][2].append(("literal", literal, None))
        end = value.find("}}", start + 2)
        if end < 0:
            fail("syntax", start)
        token = value[start + 2:end].strip()
        position = end + 2
        if token in ("/each", "/if"):
            if len(stack) == 1 or stack[-1][0] != token[1:]:
                fail("syntax", start)
            stack.pop()
            continue
        kind, path = "value", token
        for block in ("each", "if"):
            if token.startswith(f"#{block} "):
                kind, path = block, token[len(block) + 2:].strip()
        node = field(stack[-1][1], path)
        if node is None:
            fail("unknown_field", start)
        if kind == "each" and node["type"] != "list":
            fail("type", start)
        if kind == "value" and node["type"] in ("object", "list"):
            fail("type", start)
        children = []
        stack[-1][2].append((kind, path, children))
        if kind in ("each", "if"):
            if len(stack) >= MAX_DEPTH:
                fail("limit", start)
            stack.append((kind, node["items"] if kind == "each" else stack[-1][1], children))
    if len(stack) != 1:
        fail("syntax", len(value))
    return root


def skeleton(nodes):
    """Check static markup even in optional/empty blocks, before data exist."""
    return "".join(value if kind == "literal" else PLACEHOLDER if kind == "value"
                   else skeleton(children) for kind, value, children in nodes)


def render(nodes, data, *, language, html=False, origin="data"):
    chunks = []
    operations = size = 0

    def emit(value):
        nonlocal size
        size += len(value.encode("utf-8"))
        if size > RESULT_BYTES:
            raise TemplateError("limit", origin=origin, tab="html" if html else "text")
        chunks.append(value)

    def walk(parts, context):
        nonlocal operations
        for kind, path, children in parts:
            operations += 1
            if operations > MAX_OPERATIONS:
                raise TemplateError("limit", origin=origin)
            if kind == "literal":
                emit(path)
                continue
            value = context
            if path != "this" or isinstance(context, dict):
                for key in path.split("."):
                    value = value.get(key) if isinstance(value, dict) else None
            if kind == "each":
                for item in value or []:
                    operations += 1
                    if operations > MAX_OPERATIONS:
                        raise TemplateError("limit", origin=origin)
                    walk(children, item)
            elif kind == "if":
                # false and 0 are present typed values, not missing strings.
                if value is not None and value != "":
                    walk(children, context)
            else:
                if value is None:
                    value = ""
                elif type(value) is bool:
                    value = "true" if value else "false"
                elif type(value) in (int, float):
                    value = fmt(value, language=language)
                emit(escape(value, quote=True) if html else value)

    walk(nodes, data)
    return "".join(chunks)
