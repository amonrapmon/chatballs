"""Catalog and safe substitution API for the existing template library."""

from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.conversations.template_rendering import render_template
from chatballs.conversations.template_validation import LibraryValidationError
from chatballs.conversations.template_variables import variable_catalog
from chatballs.i18n import t


def _conversation_id(value):
    if type(value) is int and 0 < value <= 9223372036854775807:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit() and 0 < len(value) < 20:
        return _conversation_id(int(value))
    raise LibraryValidationError(t("conversations.template_conversation_required"))


class TemplateVariablesView(APIView):
    permission_classes = [HasCapability]
    required_capability = "conversations.view"

    def get(self, request):
        conversation_id = request.query_params.get("conversationId")
        if conversation_id is not None:
            conversation_id = _conversation_id(conversation_id)
        return Response({"items": variable_catalog(request.tenant_context, conversation_id)})


class TemplateRenderView(APIView):
    permission_classes = [HasCapability]
    required_capability = "conversations.view"

    def post(self, request, template_id):
        if not isinstance(request.data, dict) or set(request.data) != {"conversationId"}:
            raise LibraryValidationError(t("conversations.template_render_input"))
        return Response(render_template(
            request.tenant_context, template_id, _conversation_id(request.data["conversationId"]),
        ))
