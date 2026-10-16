import copy

from django.test import SimpleTestCase

from chatballs.ai.skill_templates import limits
from chatballs.ai.skill_templates.css_policy import clean_css
from chatballs.ai.skill_templates.engine import (
    compile_template,
    render_template,
    validate_templates,
)
from chatballs.ai.skill_templates.errors import TemplateError
from chatballs.ai.skill_templates.language import compile_source, render
from chatballs.ai.skill_templates.order_basis import order_basis
from chatballs.ai.skill_templates.schema import validate_data, validate_schema
from chatballs.ai.skills_validation import INSTRUCTION_MAX, SkillError, configuration


class TemplateLimitTests(SimpleTestCase):
    def setUp(self):
        self.config = order_basis(language="ru")
        self.template = self.config["templates"][0]

    def test_source_instruction_schema_configuration_and_data_byte_boundaries(self):
        limits.source("я" * (limits.SOURCE_BYTES // 2), tab="html")
        with self.assertRaises(TemplateError):
            limits.source("я" * (limits.SOURCE_BYTES // 2) + "x", tab="html")
        configuration({**self.config, "instruction": "x" * INSTRUCTION_MAX})
        with self.assertRaises(SkillError):
            configuration({**self.config, "instruction": "x" * (INSTRUCTION_MAX + 1)})
        for maximum in (limits.SCHEMA_BYTES, limits.CONFIG_BYTES, limits.DATA_BYTES):
            limits.bounded_json("x" * (maximum - 2), maximum)
            with self.assertRaises(TemplateError):
                limits.bounded_json("x" * (maximum - 1), maximum)
        with self.assertRaises(TemplateError):
            configuration({**self.config, "templates": [{**self.template, "schema": {"x": "x" * limits.SCHEMA_BYTES}}]})
        with self.assertRaises(TemplateError):
            render_template(self.template, {"x": "x" * limits.DATA_BYTES}, language="ru")
        limits.source("", tab="css")
        with self.assertRaises(TemplateError):
            compile_template({**self.template, "examples": ["x" * limits.DATA_BYTES]})

    def test_list_depth_fields_and_template_count_boundaries(self):
        data = copy.deepcopy(self.template["examples"][0])
        data["items"] = [data["items"][0]] * limits.MAX_LIST
        render_template(self.template, data, language="ru")
        data["items"] = data["items"] + [data["items"][0]]
        with self.assertRaises(TemplateError):
            render_template(self.template, data, language="ru")
        schema = {"type": "string"}
        for _ in range(limits.MAX_DEPTH):
            schema = {"type": "object", "properties": {"child": schema}}
        validate_schema(schema)
        with self.assertRaises(TemplateError):
            validate_schema({"type": "object", "properties": {"child": schema}})
        schema = {"type": "object", "properties": {f"field{i}": {"type": "string"} for i in range(limits.MAX_FIELDS - 1)}}
        validate_schema(schema)
        schema["properties"]["extra"] = {"type": "string"}
        with self.assertRaises(TemplateError):
            validate_schema(schema)
        templates = [{**self.template, "id": f"00000000-0000-4000-8000-{i:012d}"} for i in range(limits.MAX_TEMPLATES)]
        validate_templates(templates)
        with self.assertRaises(TemplateError):
            validate_templates(templates + [{**self.template}])
        with self.assertRaises(TemplateError):
            validate_templates([self.template, self.template])

    def test_result_operations_and_node_budgets_stop_expansion(self):
        # Reach the exact operation boundary with empty loops, without hitting
        # the independent output budget. Each list visit is charged too.
        nodes = [("value", "s", [])] * limits.MAX_OPERATIONS
        render(nodes, {"s": ""}, language="ru")
        with self.assertRaises(TemplateError):
            render(nodes + [("value", "s", [])], {"s": ""}, language="ru")
        render([("literal", "x" * limits.RESULT_BYTES, None)], {}, language="ru")
        with self.assertRaises(TemplateError):
            render([("literal", "x" * (limits.RESULT_BYTES + 1), None)], {}, language="ru")
        huge = {"type": "object", "properties": {"rows": {"type": "list", "items": {"type": "string"}}}}
        with self.assertRaises(TemplateError):
            validate_data(huge, {"rows": [""] * limits.MAX_NODES})
        text = "{{#each items}}" + "{{title}}" * 50 + "{{/each}}"
        template = {**self.template, "text": text}
        data = copy.deepcopy(self.template["examples"][0])
        data["items"] = [{**data["items"][0], "title": "x" * 2000}] * 20
        with self.assertRaises(TemplateError):
            render_template(template, data, language="ru")
        schema = {"type": "object", "properties": {"s": {"type": "string"}}}
        nested = "{{#if s}}" * limits.MAX_DEPTH + "x" + "{{/if}}" * limits.MAX_DEPTH
        with self.assertRaises(TemplateError):
            compile_source(nested, schema, tab="text")

    def test_css_example_string_and_metadata_budgets(self):
        clean_css("p{color:red}" * 128)
        clean_css("p{" + "color:red;" * 512 + "}")
        for css in ("p{color:red}" * 129, "p{" + "color:red;" * 513 + "}"):
            with self.assertRaises(TemplateError):
                clean_css(css)
        schema = {"type": "object", "properties": {"s": {"type": "string", "description": "x" * 500}}}
        validate_schema(schema)
        validate_data(schema, {"s": "x" * 8000})
        with self.assertRaises(TemplateError):
            validate_data(schema, {"s": "x" * 8001})
        schema["properties"]["s"]["description"] += "x"
        with self.assertRaises(TemplateError):
            validate_schema(schema)
        template = {**self.template, "examples": [{}] * 8, "name": "x" * 60, "purpose": "x" * 500}
        compile_template(template)
        for changes in ({"examples": [{}] * 9}, {"name": "x" * 61}, {"purpose": "x" * 501}):
            with self.assertRaises(TemplateError):
                compile_template({**template, **changes})
