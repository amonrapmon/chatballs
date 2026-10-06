"""Настройка установки «адреса локальной сети для инструментов агентов».

GET   instance/settings/tools-network/  — значение, кто и когда включил
PATCH instance/settings/tools-network/  — включить или выключить

Настройка открывает агентам всех организаций частные адреса сети, где стоит
установка (SPEC-0023 R-17), поэтому и читает, и меняет её только администратор
установки: менеджеру организации она ни к чему, в отличие от адресов TURN.
Сервисы самой установки и loopback закрыты при любом значении
(``integrations.tool_network``).
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.i18n import t
from chatballs.identity.audit import record_audit_event
from chatballs.identity.instance_access import IsInstanceAdmin
from chatballs.identity.instance_settings import InstanceSettings

_FIELDS = [
    "tools_private_network",
    "tools_private_network_enabled_by",
    "tools_private_network_enabled_at",
    "updated_at",
]


def tools_network_payload(row: InstanceSettings) -> dict[str, object]:
    actor = row.tools_private_network_enabled_by
    enabled_at = row.tools_private_network_enabled_at
    return {
        "enabled": row.tools_private_network,
        "enabledBy": {"id": actor.id, "name": actor.full_name or actor.email} if actor else None,
        "enabledAt": enabled_at.isoformat() if enabled_at else None,
    }


class InstanceToolsNetworkView(APIView):
    permission_classes = [IsInstanceAdmin]

    def get(self, request: Request) -> Response:
        return Response({"toolsNetwork": tools_network_payload(InstanceSettings.load())})

    def patch(self, request: Request) -> Response:
        body = request.data if isinstance(request.data, dict) else {}
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            message = t("settings.tools_network_enabled_required")
            return Response({"detail": message, "errors": {"enabled": message}}, status=400)
        row = InstanceSettings.load()
        if enabled != row.tools_private_network:
            row.tools_private_network = enabled
            row.tools_private_network_enabled_by = request.user if enabled else None
            row.tools_private_network_enabled_at = timezone.now() if enabled else None
            row.save(update_fields=_FIELDS)
            record_audit_event(
                action=(
                    "administration.tools_private_network_enabled"
                    if enabled
                    else "administration.tools_private_network_disabled"
                ),
                actor=request.user,
                organization=None,
                object_type="InstanceSettings",
                object_id=str(row.pk),
                request=request,
            )
        return Response({"toolsNetwork": tools_network_payload(row)})
