"""Significant language/schema behavior; no running-environment fixtures."""

import copy

from django.test import SimpleTestCase

from chatballs.ai.skill_templates.engine import compile_template, render_template
from chatballs.ai.skill_templates.errors import TemplateError
from chatballs.ai.skill_templates.order_basis import order_basis


class TemplateLanguageTests(SimpleTestCase):
    def setUp(self):
        self.template = order_basis(language="ru")["templates"][0]
        self.data = self.template["examples"][0]

    def test_examples_and_locale_are_rendered_without_arithmetic(self):
        for language, amount in (("ru", "20\xa0200"), ("en", "20,200")):
            for template in order_basis(language=language)["templates"]:
                for data in template["examples"]:
                    result = render_template(template, data, language=language)
                    self.assertNotIn("{{", result["text"] + result["contentHtml"])
                    self.assertIn(data["order_no"], result["text"])
                    self.assertEqual(result["presentation"]["sandbox"], "")
                    self.assertIn("default-src", result["presentation"]["srcDoc"])
            result = render_template(self.template, self.data, language=language)
            self.assertIn(amount, result["text"])
        changed = copy.deepcopy(self.data)
        changed["total"] = 123
        self.assertIn("123 ₽", render_template(self.template, changed, language="ru")["text"])

    def test_nested_objects_each_context_and_scalar_lists(self):
        template = copy.deepcopy(self.template)
        template["schema"] = {"type": "object", "properties": {
            "groups": {"type": "list", "items": {"type": "object", "properties": {
                "info": {"type": "object", "properties": {"name": {"type": "string"}}},
                "values": {"type": "list", "items": {"type": "number"}},
            }}},
        }}
        template["html"] = "<p>{{#each groups}}{{ info.name }}:{{#each values}}{{ this }};{{/each}}{{/each}}</p>"
        template["text"] = "{{#each groups}}{{ info.name }}:{{#each values}}{{ this }};{{/each}}{{/each}}"
        result = render_template(template, {"groups": [{"info": {"name": "First"}, "values": [0, 2]}]}, language="en")
        self.assertEqual(result["text"], "First:0;2;")

    def test_if_presence_retains_zero_false_and_hides_missing_null_empty(self):
        template = copy.deepcopy(self.template)
        template["schema"] = {"type": "object", "properties": {
            "n": {"type": "number"}, "b": {"type": "boolean"}, "s": {"type": "string"},
        }}
        template["text"] = "{{#if n}}n={{n}}{{/if}}{{#if b}}b={{b}}{{/if}}{{#if s}}s={{s}}{{/if}}{{s}}"
        template["html"] = "<p>" + template["text"] + "</p>"
        for data in ({"n": 0, "b": False}, {"n": 0, "b": False, "s": None}, {"n": 0, "b": False, "s": ""}):
            self.assertEqual(render_template(template, data, language="ru")["text"], "n=0b=false")
        status = order_basis(language="ru")["templates"][1]
        result = render_template(status, status["examples"][1], language="ru")
        self.assertNotIn("Ожидаемое время", result["text"])
        self.assertNotIn('class="eta"', result["contentHtml"])

    def test_unknown_fields_types_required_values_and_unicode_fail_safely(self):
        for data in (
            {**self.data, "secret": "DO-NOT-ECHO"}, {**self.data, "total": "20200"},
            {**self.data, "total": True}, {**self.data, "total": None},
            {**self.data, "order_no": ""}, {**self.data, "items": [None]},
            {**self.data, "total": 10**1000}, {**self.data, "order_no": "\ud800"},
        ):
            with self.subTest(data=list(data)), self.assertRaises(TemplateError) as error:
                render_template(self.template, data, language="ru", origin="example")
            self.assertEqual(error.exception.detail["origin"], "example")
            self.assertNotIn("DO-NOT-ECHO", str(error.exception.detail))
        missing = {key: value for key, value in self.data.items() if key != "total"}
        with self.assertRaises(TemplateError) as error:
            render_template(self.template, missing, language="ru")
        self.assertEqual(error.exception.detail["errors"][0]["path"], "total")

    def test_language_rejects_code_raw_access_and_unclosed_blocks_at_save(self):
        for code in ("{{ unknown }}", "{{items.title}}", "{{#each total}}x{{/each}}",
                     "{{#each items}}{{order_no}}{{/each}}", "{{#each items}}",
                     "{{/if}}", "{{#if order_no}}x{{/each}}", "{{{ order_no }}}",
                     "{{ total + 1 }}", "{{ fmt(total) }}", "{{ include 'x' }}",
                     "{{ __class__.__mro__ }}", "{{ items }}", "}}", "{{"):
            with self.subTest(code=code), self.assertRaises(TemplateError):
                compile_template({**self.template, "text": code})
        with self.assertRaises(TemplateError) as error:
            compile_template({**self.template, "text": "First\n{{ unknown }}"})
        self.assertEqual(error.exception.detail["errors"][0]["line"], "2")

    def test_invalid_examples_do_not_invalidate_configuration(self):
        template = {**self.template, "examples": [{}, {"total": "incomplete"}]}
        compile_template(template)
        with self.assertRaises(TemplateError) as error:
            render_template(template, template["examples"][0], language="ru", origin="example")
        self.assertEqual(error.exception.detail["origin"], "example")

    def test_malformed_nested_schema_is_a_safe_configuration_error(self):
        for schema in (
            {"type": []}, {"type": {}},
            {"type": "object", "properties": {"bad": {"type": []}}},
            {"type": "object", "properties": {"rows": {"type": "list", "items": None}}},
            {"type": "object", "properties": {"bad": {"type": "string", "required": "true"}}},
        ):
            with self.subTest(schema=schema), self.assertRaises(TemplateError) as error:
                compile_template({**self.template, "schema": schema})
            self.assertEqual(error.exception.detail["origin"], "configuration")
