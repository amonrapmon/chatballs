"""tinycss2 parses rules, declarations and values before positive validation."""

import tinycss2

from .css_syntax import balanced
from .errors import TemplateError
from .limits import source
from .selector_policy import valid_selector

PROPERTIES = set("""
color background background-color border border-top border-bottom border-left border-right
border-color border-width border-style border-radius border-collapse border-spacing
padding padding-top padding-bottom padding-left padding-right
margin margin-top margin-bottom margin-left margin-right
display flex flex-direction flex-wrap flex-grow flex-shrink flex-basis align-items align-self
justify-content gap row-gap column-gap grid-template-columns
width min-width max-width height min-height max-height box-sizing
font-size font-weight font-family font-style line-height letter-spacing
text-align text-decoration white-space overflow-wrap word-break vertical-align
order counter-reset counter-increment content
""".split())
FUNCTIONS = {"rgb", "rgba", "minmax", "repeat", "counter"}


def clean_css(value):
    source(value, tab="css")

    def fail(token=None):
        line = getattr(token, "source_line", 1)
        column = getattr(token, "source_column", 1)
        offset = sum(len(part) for part in value.splitlines(keepends=True)[:line - 1]) + column - 1
        raise TemplateError("css_policy", tab="css", source=value, offset=offset)

    def values(tokens, depth=0, *, strings=False):
        if depth > 4:
            fail()
        for token in tokens:
            if token.type == "function":
                if token.lower_name not in FUNCTIONS:
                    fail(token)
                values(token.arguments, depth + 1)
            elif token.type == "string" and strings:
                if "<" in token.value or len(token.value) > 100:
                    fail(token)
            elif token.type == "dimension":
                if token.lower_unit not in {"px", "em", "rem", "fr"} or not 0 <= token.value <= 2000:
                    fail(token)
            elif token.type in {"number", "percentage"}:
                if not 0 <= token.value <= 2000:
                    fail(token)
            elif token.type == "literal":
                if token.value not in {",", "/", "-"}:
                    fail(token)
            elif token.type not in {"ident", "hash", "whitespace"}:
                fail(token)

    if not balanced(value):
        fail()
    output = []
    rules = tinycss2.parse_stylesheet(value, skip_comments=True, skip_whitespace=True)
    if len(rules) > 128:
        fail()
    declarations_count = 0
    for rule in rules:
        if rule.type != "qualified-rule":
            fail(rule)
        if not valid_selector(rule.prelude):
            fail(rule)
        declarations = tinycss2.parse_declaration_list(rule.content, skip_comments=True, skip_whitespace=True)
        cleaned = []
        for declaration in declarations:
            declarations_count += 1
            if (declarations_count > 512 or declaration.type != "declaration"
                    or declaration.lower_name not in PROPERTIES or declaration.important):
                fail(declaration)
            values(declaration.value, strings=declaration.lower_name == "content")
            cleaned.append(f"{declaration.lower_name}:{tinycss2.serialize(declaration.value)};")
        output.append(tinycss2.serialize(rule.prelude) + "{" + "".join(cleaned) + "}")
    return "\n".join(output)
