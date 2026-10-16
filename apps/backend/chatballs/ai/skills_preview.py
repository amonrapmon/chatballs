"""Read-only administrative validation/preview of an unsaved local draft."""

from rest_framework.response import Response

from chatballs.ai.skill_templates.engine import render_template
from chatballs.ai.skill_templates.errors import TemplateError
from chatballs.ai.skill_templates.schema import validate_data, validate_schema
from chatballs.ai.skills_queries import load
from chatballs.ai.skills_validation import configuration
from chatballs.ai.skills_views import SkillView
from chatballs.i18n import customer_language


class SkillValidationView(SkillView):
    def post(self, request, skill_id=None):
        if skill_id is not None:
            load(request.tenant_context, skill_id)
        raw = self.body(request, ["configuration"])
        configuration(raw["configuration"])
        return Response({"valid": True})


class SkillPreviewView(SkillView):
    def post(self, request, skill_id=None):
        if skill_id is not None:
            load(request.tenant_context, skill_id)
        raw = self.body(request, ["configuration", "templateId", "data"])
        try:
            values = configuration(raw["configuration"])
        except TemplateError as error:
            # Code and example errors are independent. Report both even when
            # compilation prevents rendering; never run invalid source.
            templates = raw["configuration"].get("templates", [])
            template = next((item for item in templates if isinstance(item, dict)
                             and item.get("id") == raw["templateId"]), None) if isinstance(templates, list) else None
            if template is not None:
                try:
                    schema = validate_schema(template.get("schema"))
                except TemplateError:
                    pass
                else:
                    try:
                        validate_data(schema, raw["data"], origin="example")
                    except TemplateError as data_error:
                        raise TemplateError.combined(error.detail["errors"] + data_error.detail["errors"]) from None
            raise
        template = next((item for item in values["templates"] if item["id"] == raw["templateId"]), None)
        if template is None:
            raise TemplateError("unknown_field", path="templateId")
        return Response(render_template(
            template, raw["data"], language=customer_language(request.tenant_context.organization), origin="example",
        ))


class SkillBasisView(SkillView):
    def get(self, request):
        from chatballs.ai.skill_templates.order_basis import order_basis

        return Response({"basisId": "orders-v1", "configuration": order_basis(
            language=customer_language(request.tenant_context.organization),
        )})
