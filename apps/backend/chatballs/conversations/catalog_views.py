"""Organization label catalog and compatibility exports for reply templates."""

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.conversations.models import ConversationLabel
from chatballs.i18n import t


def _label_payload(label: ConversationLabel) -> dict[str, object]:
    return {"id": label.id, "name": label.name, "color": label.color}


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


from chatballs.conversations.template_views import (  # noqa: E402, F401
    ReplyTemplateDetailView,
    ReplyTemplateListView,
)
