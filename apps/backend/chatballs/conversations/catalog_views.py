"""Organization label and reply template catalogs."""

import re

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.conversations.models import ConversationLabel, ReplyTemplate
from chatballs.i18n import t


def _label_payload(label: ConversationLabel) -> dict[str, object]:
    return {"id": label.id, "name": label.name, "color": label.color}


# Переменные шаблонов ответов: подставляет их интерфейс оператора при вставке
# шаблона (internal-ui, conversations/templateVariables.ts — тот же список).
TEMPLATE_VARIABLES = frozenset({"client_name", "operator_name", "company"})
_TEMPLATE_TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def _template_text_error(text: str) -> Response | None:
    if not text:
        return Response({"detail": t("conversations.template_text_required")}, status=400)
    unknown = sorted(
        {match.group(0) for match in _TEMPLATE_TOKEN.finditer(text) if match.group(1) not in TEMPLATE_VARIABLES}
    )
    if unknown:
        return Response(
            {"detail": t("conversations.template_unknown_variables", names=", ".join(unknown))},
            status=400,
        )
    return None


def _template_payload(template: ReplyTemplate) -> dict[str, object]:
    return {
        "id": template.id,
        "title": template.title,
        "text": template.text,
        "updatedAt": template.updated_at.isoformat(),
    }


class LabelListView(APIView):
    """Словарь меток организации. Создание — лёгкое действие оператора
    («+ Добавить» в карточке), правка/удаление — администратора."""

    permission_classes = [HasCapability]
    required_capabilities = {
        "GET": "conversations.view",
        "POST": "conversations.operate",
    }

    def get(self, request: Request) -> Response:
        labels = ConversationLabel.objects.filter(
            organization_id=request.tenant_context.organization_id
        )
        return Response({"items": [_label_payload(label) for label in labels]})

    def post(self, request: Request) -> Response:
        name = str(request.data.get("name", "")).strip()
        color = str(request.data.get("color", "")).strip()
        if not name or len(name) > 60:
            return Response({"detail": t("conversations.label_name_length")}, status=400)
        if len(color) > 20:
            return Response({"detail": t("conversations.invalid_colour")}, status=400)
        existing = ConversationLabel.objects.filter(
            organization_id=request.tenant_context.organization_id, name__iexact=name
        ).first()
        if existing is not None:
            return Response({"label": _label_payload(existing)})
        label = ConversationLabel.objects.create(
            organization_id=request.tenant_context.organization_id,
            name=name,
            color=color,
        )
        return Response({"label": _label_payload(label)}, status=201)


class LabelDetailView(APIView):
    permission_classes = [HasCapability]
    required_capabilities = {"PATCH": "settings.manage", "DELETE": "settings.manage"}

    def _label(self, request: Request, label_id: int) -> ConversationLabel:
        return ConversationLabel.objects.get(
            organization_id=request.tenant_context.organization_id, id=label_id
        )

    def patch(self, request: Request, label_id: int) -> Response:
        try:
            label = self._label(request, label_id)
        except ConversationLabel.DoesNotExist:
            return Response({"detail": t("conversations.label_not_found")}, status=404)
        if "name" in request.data:
            name = str(request.data.get("name", "")).strip()
            if not name or len(name) > 60:
                return Response({"detail": t("conversations.label_name_length")}, status=400)
            label.name = name
        if "color" in request.data:
            color = str(request.data.get("color", "")).strip()
            if len(color) > 20:
                return Response({"detail": t("conversations.invalid_colour")}, status=400)
            label.color = color
        label.save()
        return Response({"label": _label_payload(label)})

    def delete(self, request: Request, label_id: int) -> Response:
        try:
            label = self._label(request, label_id)
        except ConversationLabel.DoesNotExist:
            return Response({"detail": t("conversations.label_not_found")}, status=404)
        label.delete()
        return Response(status=204)


class ReplyTemplateListView(APIView):
    permission_classes = [HasCapability]
    required_capabilities = {
        "GET": "conversations.view",
        "POST": "settings.manage",
    }

    def get(self, request: Request) -> Response:
        templates = ReplyTemplate.objects.filter(
            organization_id=request.tenant_context.organization_id
        )
        return Response({"items": [_template_payload(item) for item in templates]})

    def post(self, request: Request) -> Response:
        title = str(request.data.get("title", "")).strip()
        text = str(request.data.get("text", "")).strip()
        if not title or len(title) > 120:
            return Response({"detail": t("conversations.template_name_length")}, status=400)
        if error := _template_text_error(text):
            return error
        if ReplyTemplate.objects.filter(
            organization_id=request.tenant_context.organization_id, title__iexact=title
        ).exists():
            return Response({"detail": t("conversations.template_name_taken")}, status=409)
        template = ReplyTemplate.objects.create(
            organization_id=request.tenant_context.organization_id,
            title=title,
            text=text,
        )
        return Response({"template": _template_payload(template)}, status=201)


class ReplyTemplateDetailView(APIView):
    permission_classes = [HasCapability]
    required_capabilities = {"PATCH": "settings.manage", "DELETE": "settings.manage"}

    def _template(self, request: Request, template_id: int) -> ReplyTemplate:
        return ReplyTemplate.objects.get(
            organization_id=request.tenant_context.organization_id, id=template_id
        )

    def patch(self, request: Request, template_id: int) -> Response:
        try:
            template = self._template(request, template_id)
        except ReplyTemplate.DoesNotExist:
            return Response({"detail": t("conversations.template_not_found")}, status=404)
        if "title" in request.data:
            title = str(request.data.get("title", "")).strip()
            if not title or len(title) > 120:
                return Response({"detail": t("conversations.template_name_length")}, status=400)
            if ReplyTemplate.objects.filter(
                organization_id=template.organization_id, title__iexact=title
            ).exclude(id=template.id).exists():
                return Response({"detail": t("conversations.template_name_taken")}, status=409)
            template.title = title
        if "text" in request.data:
            text = str(request.data.get("text", "")).strip()
            if error := _template_text_error(text):
                return error
            template.text = text
        template.save()
        return Response({"template": _template_payload(template)})

    def delete(self, request: Request, template_id: int) -> Response:
        try:
            template = self._template(request, template_id)
        except ReplyTemplate.DoesNotExist:
            return Response({"detail": t("conversations.template_not_found")}, status=404)
        template.delete()
        return Response(status=204)
