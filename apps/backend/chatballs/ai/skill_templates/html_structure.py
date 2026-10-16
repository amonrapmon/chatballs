"""Template blocks preserve HTML structure; values occupy quoted attributes/text."""

from .errors import TemplateError
from .html_policy import clean_html
from .language import skeleton


def validate_structure(source, nodes):
    in_tag = False
    quote = None
    index = 0
    while index < len(source):
        if source.startswith("{{", index):
            end = source.index("}}", index)  # language compilation already succeeded
            token = source[index + 2:end].strip()
            if in_tag and (quote is None or token.startswith(("#", "/"))):
                raise TemplateError("syntax", tab="html", source=source, offset=index)
            index = end + 2
            continue
        char = source[index]
        if in_tag:
            if quote:
                if char == quote:
                    quote = None
            elif char in {"'", '"'}:
                quote = char
            elif char == ">":
                in_tag = False
        elif char == "<":
            in_tag = True
        index += 1
    for kind, _, children in nodes:
        if kind not in {"if", "each"}:
            continue
        # Check every branch, including branches not exercised by any example.
        # Table rows/cells need their HTML5 fragment parsing context.
        markup = skeleton(children)
        error = None
        for container in ("div", "table", "tbody", "tr"):
            try:
                clean_html(markup, static=True, container=container)
                error = None
                break
            except TemplateError as caught:
                error = caught
        if error:
            raise error
        validate_structure(markup, children)
