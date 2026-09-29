"""Очистка SVG-иконки виджета: опасное вырезается, картинка остаётся (SPEC-0021 R-4)."""

from __future__ import annotations

from django.test import SimpleTestCase

from chatballs.webchat.svg_sanitizer import UnsafeSvg, sanitize_svg

HARMFUL_SVG = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     viewBox="0 0 64 64" onload="alert('load')">
  <script type="text/javascript">alert('script')</script>
  <foreignObject width="10" height="10">
    <div xmlns="http://www.w3.org/1999/xhtml" onclick="alert('html')">x</div>
  </foreignObject>
  <defs><circle id="dot" r="4"/></defs>
  <a xlink:href="javascript:alert('link')"><rect width="8" height="8" onclick="alert('click')"/></a>
  <a href="java&#9;script:alert('tab')"><rect width="4" height="4"/></a>
  <image href="https://evil.example/pixel.png" width="1" height="1"/>
  <image xlink:href="data:image/svg+xml;base64,PHN2Zy8+" width="1" height="1"/>
  <use xlink:href="#dot" x="32" y="32"/>
  <use href="https://evil.example/sprite.svg#icon"/>
  <set attributeName="href" to="javascript:alert('smil')"/>
  <animate attributeName="onclick" values="alert('smil')"/>
  <animate attributeName="opacity" values="0;1" dur="1s"/>
  <rect width="16" height="16" fill="url(#dot)" style="fill:url(https://evil.example/x)"/>
  <style>@import url(https://evil.example/a.css); .mark { fill: #1677ff; }</style>
  <circle class="mark" cx="32" cy="32" r="30"/>
</svg>
"""


class SvgSanitizerTests(SimpleTestCase):
    def test_harmful_parts_are_removed(self) -> None:
        cleaned = sanitize_svg(HARMFUL_SVG).decode("utf-8")
        lowered = cleaned.lower()

        for forbidden in (
            "<script",
            "foreignobject",
            "onload",
            "onclick",
            "javascript:",
            "evil.example",
            "data:",
            "@import",
            "alert(",
        ):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, lowered)

    def test_picture_and_local_references_stay(self) -> None:
        cleaned = sanitize_svg(HARMFUL_SVG).decode("utf-8")

        self.assertIn('viewBox="0 0 64 64"', cleaned)
        self.assertIn('<circle class="mark" cx="32" cy="32" r="30" />', cleaned)
        self.assertIn('xlink:href="#dot"', cleaned)
        self.assertIn('fill="url(#dot)"', cleaned)
        self.assertIn('attributeName="opacity"', cleaned)
        self.assertTrue(cleaned.startswith("<?xml"))
        self.assertIn('<svg xmlns="http://www.w3.org/2000/svg"', cleaned)

    def test_svg_without_namespace_gets_it(self) -> None:
        cleaned = sanitize_svg(b'<svg viewBox="0 0 4 4"><path d="M0 0h4v4z"/></svg>')

        self.assertIn(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 4">', cleaned)
        self.assertIn(b'<path d="M0 0h4v4z" />', cleaned)

    def test_unreadable_svg_is_refused(self) -> None:
        samples = {
            "doctype": b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>',
            "broken xml": b'<svg xmlns="http://www.w3.org/2000/svg"><rect></svg>',
            "not svg": b"<html><body>hi</body></html>",
            "foreign root": b'<svg xmlns="http://evil.example/ns"/>',
        }
        for name, sample in samples.items():
            with self.subTest(name), self.assertRaises(UnsafeSvg):
                sanitize_svg(sample)
