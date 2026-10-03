"""Очистка HTML текста согласия по белому списку (SPEC-0020 R-14)."""

from __future__ import annotations

from django.test import SimpleTestCase

from chatballs.webchat.consent_html import clean_consent_html

LINK_ATTRS = 'target="_blank" rel="noopener noreferrer nofollow"'


class ConsentHtmlTests(SimpleTestCase):
    def test_allowed_tags_are_kept(self):
        text = (
            "<p>Абзац <strong>жирный</strong> <b>b</b> <em>курсив</em> <i>i</i> <u>u</u><br>строка</p>"
            "<ul><li>раз</li></ul><ol><li>два</li></ol>"
        )
        self.assertEqual(clean_consent_html(text), text)

    def test_link_keeps_only_href_and_gets_target_and_rel(self):
        cleaned = clean_consent_html(
            '<a href="https://example.ru/privacy" class="x" id="y" target="_self" rel="opener">политика</a>'
        )
        self.assertEqual(cleaned, f'<a href="https://example.ru/privacy" {LINK_ATTRS}>политика</a>')

    def test_allowed_url_schemes_are_kept(self):
        for href in ("http://example.ru", "https://example.ru/?a=1", "mailto:dpo@example.ru", "tel:+79000000000"):
            with self.subTest(href=href):
                self.assertEqual(
                    clean_consent_html(f'<a href="{href}">x</a>'), f'<a href="{href}" {LINK_ATTRS}>x</a>'
                )

    def test_javascript_and_other_schemes_lose_href(self):
        unsafe = (
            "javascript:alert(1)", "JaVaScRiPt:alert(1)", " java\tscript:alert(1)", "vbscript:x",
            "data:text/html,<b>x</b>", "ftp://example.ru", "/privacy", "//evil.example", "#top",
        )
        for href in unsafe:
            with self.subTest(href=href):
                self.assertEqual(clean_consent_html(f'<a href="{href}">x</a>'), f"<a {LINK_ATTRS}>x</a>")

    def test_script_and_style_are_removed_with_content(self):
        cleaned = clean_consent_html("До<script>alert(1)</script><style>p{color:red}</style>После")
        self.assertEqual(cleaned, "ДоПосле")

    def test_event_handlers_and_other_attributes_are_removed(self):
        cleaned = clean_consent_html(
            '<p onclick="alert(1)" style="color:red">a</p><b onmouseover="x()">b</b>'
            '<a href="https://example.ru" onclick="x()">c</a>'
        )
        self.assertEqual(cleaned, f'<p>a</p><b>b</b><a href="https://example.ru" {LINK_ATTRS}>c</a>')

    def test_other_tags_are_removed_but_text_is_kept(self):
        cleaned = clean_consent_html(
            "<h1>Заголовок</h1><div>блок</div><span>строка</span><img src=x onerror=alert(1)>"
            "<iframe src=\"https://evil.example\">рамка</iframe><!-- комментарий -->"
        )
        self.assertEqual(cleaned, "Заголовокблокстрокарамка")

    def test_plain_text_is_kept_and_newlines_are_not_converted(self):
        self.assertEqual(clean_consent_html(" Согласие «в кавычках» "), "Согласие «в кавычках»")
        self.assertEqual(clean_consent_html("первая\nвторая"), "первая\nвторая")

    def test_cleaning_is_idempotent(self):
        once = clean_consent_html(
            'A & B <a href="https://example.ru/?a=1&b=2">x</a> <a href="/rel">y</a><script>z</script>'
        )
        self.assertEqual(clean_consent_html(once), once)
