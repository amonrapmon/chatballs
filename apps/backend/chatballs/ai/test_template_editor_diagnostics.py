"""Editor diagnostics share the production compiler and data validator."""

import copy

from django.test import SimpleTestCase, TransactionTestCase

from chatballs.ai.skill_templates.engine import compile_template, render_template
from chatballs.ai.skill_templates.errors import TemplateError
from chatballs.ai.skill_templates.order_basis import order_basis
from chatballs.ai.skill_templates.schema import validate_data, validate_schema
from chatballs.ai.skills_test_support import SkillsSetup


class TemplateEditorDiagnosticsTests(SimpleTestCase):
    def setUp(self):
        self.template = order_basis(language="ru")["templates"][0]

    def test_independent_tabs_and_data_errors_are_localized_without_echoing_values(self):
        template = {**self.template, "html": "<p>{{ discount }}</p>", "text": "{{#each items}}\n{{qty}}"}
        with self.assertRaises(TemplateError) as caught:
            compile_template(template)
        errors = caught.exception.detail["errors"]
        self.assertEqual([error["tab"] for error in errors], ["html", "text"])
        self.assertTrue(all(error.get("line") for error in errors))
        data = copy.deepcopy(self.template["examples"][0])
        data["items"][0]["qty"] = "PRIVATE-два"
        data.pop("total")
        data["discount"] = 50
        with self.assertRaises(TemplateError) as caught:
            validate_data(self.template["schema"], data, origin="example")
        errors = caught.exception.detail["errors"]
        self.assertEqual({error["path"] for error in errors}, {"discount", "items[0].qty", "total"})
        self.assertTrue(all(error["origin"] == "example" for error in errors))
        self.assertNotIn("PRIVATE", str(caught.exception.detail))

    def test_invalid_examples_remain_saveable_and_valid_preview_matches_the_snapshot(self):
        template = {**self.template, "examples": [{"total": "два"}]}
        compile_template(template)
        original = self.template["examples"][1]
        preview = render_template(template, original, language="ru", origin="example")
        self.assertEqual(preview, render_template(template, original, language="ru"))
        self.assertEqual(preview["contentHtml"].count('class="item"'), 7)
        self.assertIn("93\xa0100", preview["text"])
        self.assertEqual(template["exampleNames"], ["Короткий", "Длинный"])

    def test_unknown_reference_and_unclosed_each_are_both_reported_in_one_tab(self):
        template = {**self.template, "html": '<div>{{#each items}}\n<p>{{ discount }}</p></div>'}
        with self.assertRaises(TemplateError) as caught:
            compile_template(template)
        errors = caught.exception.detail["errors"]
        self.assertEqual({error["code"] for error in errors}, {"unknown_field", "syntax"})
        self.assertEqual({error["line"] for error in errors}, {"1", "2"})


class TemplateEditorPreviewAPITests(SkillsSetup, TransactionTestCase):
    def test_field_order_survives_the_database_and_invalid_order_is_rejected(self):
        config = order_basis(language="ru")
        saved = self.create_skill(**config)
        template = self.client.get(self.detail(saved)).json()["skill"]["templates"][0]
        props = template["schema"]["properties"]
        self.assertEqual(sorted(props, key=lambda key: props[key]["order"]), ["order_no", "items", "total"])
        for order in (True, -1, 128, "1"):
            with self.subTest(order=order), self.assertRaises(TemplateError):
                validate_schema({"type": "object", "properties": {"value": {"type": "string", "order": order}}})

    def test_malformed_selected_template_stays_a_validation_error(self):
        config = order_basis(language="ru")
        identifier = config["templates"][0]["id"]
        config["templates"] = [{"id": identifier}]
        response = self.client.post(self.url + "preview/", {
            "configuration": config, "templateId": identifier, "data": {},
        }, format="json")
        self.assertEqual(response.status_code, 400, response.content)

    def test_preview_combines_code_and_example_diagnostics_without_saving(self):
        config = order_basis(language="ru")
        template = config["templates"][0]
        template["html"] = '<div>{{#each items}}\n<p>{{ discount }}</p></div>'
        data = copy.deepcopy(template["examples"][0])
        data["items"][0]["qty"] = "два"
        data.pop("total")
        response = self.client.post(self.url + "preview/", {
            "configuration": config, "templateId": template["id"], "data": data,
        }, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        errors = response.json()["errors"]
        self.assertEqual({error["code"] for error in errors}, {"unknown_field", "syntax", "type", "required"})
        self.assertEqual({error["origin"] for error in errors}, {"configuration", "example"})
        from chatballs.ai.skills_models import Skill

        self.assertFalse(Skill.objects.exists())
