from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.i18n import t
from chatballs.identity.audit import record_audit_event
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.integrations.selectors import integration_for_context
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.tenancy.ingress import widget_asset_route
from chatballs.tenancy.lookup import load_organization
from chatballs.webchat.assets import upload_widget_asset, widget_asset_url
from chatballs.webchat.models import WidgetAsset

# Адрес иконки неизменен: каждая загрузка получает новый UUID.
_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"


class WidgetAssetUploadView(APIView):
    """Загрузка иконки кнопки или шапки веб-виджета → ``{ url }``."""

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [HasCapability]
    required_capability = "integrations.manage"

    def post(self, request: Request, integration_id: int) -> Response:
        try:
            integration = integration_for_context(
                context=request.tenant_context, integration_id=integration_id
            )
        except Integration.DoesNotExist:
            integration = None
        if integration is None or integration.provider != IntegrationProvider.WEB:
            return Response({"detail": t("settings.integration_not_found")}, status=404)
        upload = request.FILES.get("file")
        if upload is None:
            detail = t("webchat.asset_choose_file")
            return Response({"detail": detail, "errors": {"file": detail}}, status=400)
        try:
            asset = upload_widget_asset(
                context=request.tenant_context,
                integration=integration,
                upload=upload,
                uploaded_by=request.user,
            )
        except ValidationError as error:
            detail = error.message_dict["file"][0]
            return Response({"detail": detail, "errors": {"file": detail}}, status=400)
        record_audit_event(
            action="integrations.widget_asset_uploaded",
            actor=request.user,
            organization=request.tenant_context.organization,
            object_type="Integration",
            object_id=str(integration.id),
            request=request,
        )
        return Response({"url": widget_asset_url(asset)}, status=201)


class WidgetAssetView(APIView):
    """Иконка виджета по публичной ссылке.

    Её показывает лоадер на чужом сайте, где нет сессии: защита —
    непредсказуемый UUID и резолв организации через ingress-каталог.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request: Request, public_id) -> FileResponse:
        route = widget_asset_route(str(public_id))
        organization = load_organization(route.organization_id) if route else None
        if organization is None:
            raise Http404
        with tenant_atomic(TenantContext.for_resource(organization)):
            asset = WidgetAsset.objects.filter(
                id=route.resource_id, public_id=public_id, organization=organization
            ).first()
            if asset is None:
                raise Http404
            opened_file = asset.file.open("rb")
            content_type = asset.content_type
        response = FileResponse(opened_file, content_type=content_type)
        # SVG очищен при загрузке; заголовки — второй рубеж на случай, если
        # адрес откроют как документ: ничего не исполнять, никуда не ходить,
        # тип не угадывать. Картинку можно встраивать на любой сайт.
        response["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
        response["X-Content-Type-Options"] = "nosniff"
        response["Cross-Origin-Resource-Policy"] = "cross-origin"
        response["Cache-Control"] = _IMMUTABLE_CACHE
        return response
