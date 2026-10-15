"""Parse HTML5, reject outside the positive policy, serialize and sanitize."""

import re
from urllib.parse import urlsplit

import html5lib
import nh3

from .errors import TemplateError
from .language import PLACEHOLDER

TAGS = set("div span p br strong b em i small ul ol li table thead tbody tr th td a h2 h3 hr svg path circle line polyline".split())
ATTRS = {"class", "title"}
SVG_ATTRS = {"viewBox", "width", "height", "fill", "stroke", "stroke-width",
             "stroke-linecap", "stroke-linejoin", "d", "cx", "cy", "r", "x1", "x2", "y1", "y2", "points"}


def safe_uri(value):
    if any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme.lower() in {"https", "http"} and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None and parsed.port != 0)
    except ValueError:
        return False


def clean_html(markup, *, static=False, origin="configuration", container="div"):
    def fail(offset=0):
        raise TemplateError("html_policy", tab="html", origin=origin, source=markup, offset=offset)

    parser = html5lib.HTMLParser(strict=True, namespaceHTMLElements=False)
    try:
        tree = parser.parseFragment(markup, container=container)
    except html5lib.html5parser.ParseError:
        line, column = parser.tokenizer.stream.position()
        fail(sum(len(part) for part in markup.splitlines(keepends=True)[:line - 1]) + max(0, column - 1))
    for node in tree.iter():
        if node is tree:
            continue
        if not isinstance(node.tag, str):
            fail()  # comments, processing instructions and doctypes
        tag = node.tag.rsplit("}", 1)[-1]
        if tag not in TAGS:
            fail(max(0, markup.find("<" + tag)))
        svg = node.tag.startswith("{http://www.w3.org/2000/svg}")
        if (tag in {"svg", "path", "circle", "line", "polyline"}) != svg:
            fail()
        for key, value in list(node.attrib.items()):
            if key in ATTRS:
                if key == "class" and not re.fullmatch(r"[A-Za-z0-9_ -]{0,256}", value):
                    fail()
            elif tag == "a" and key == "href":
                if not (static and value == PLACEHOLDER) and not safe_uri(value):
                    fail(max(0, markup.find("href")))
            elif svg and key in SVG_ATTRS:
                # No references, URLs, styles, animation or namespaces in SVG.
                if not re.fullmatch(r"[A-Za-z0-9#., +\-]*", value) or PLACEHOLDER in value:
                    fail()
                if key in {"fill", "stroke"} and not re.fullmatch(r"none|currentColor|#[0-9a-fA-F]{3,8}", value):
                    fail()
                if key not in {"fill", "stroke", "stroke-linecap", "stroke-linejoin"} and len(value) > 1000:
                    fail()
            else:
                fail(max(0, markup.find(key)))
        if tag == "a":
            node.set("rel", "noopener noreferrer")
            node.set("referrerpolicy", "no-referrer")
            node.set("target", "_blank")
    serialized = html5lib.serialize(tree, tree="etree", quote_attr_values="always", omit_optional_tags=False)
    # Defense in depth after interpolation. No application data is restored later.
    attributes = {"*": ATTRS, "a": {"href", "rel", "referrerpolicy", "target"}}
    for tag in ("svg", "path", "circle", "line", "polyline"):
        attributes[tag] = SVG_ATTRS | ATTRS
    return nh3.clean(serialized, tags=TAGS, attributes=attributes,
                     url_schemes={"http", "https"}, link_rel=None)
