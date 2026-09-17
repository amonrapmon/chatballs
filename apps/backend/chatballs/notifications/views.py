from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.i18n import t
from chatballs.notifications.binding import deep_link, issue_binding_code, notifier_integrations
from chatballs.notifications.models import (
    MessengerBinding,
    NotificationRead,
    NotificationTransport,
)
from chatballs.notifications.preferences import (
    preference_for,
    preference_types,
    update_preference,
)
from chatballs.notifications.selectors import unread_for, visible_for
from chatballs.notifications.serializers import notification_payload
from chatballs.notifications.services import TYPE_META, mark_read

_LIST_LIMIT = 50


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        items = list(visible_for(request.tenant_context)[:_LIST_LIMIT])
        read_ids = set(
            NotificationRead.objects.filter(user=request.user, notification__in=items).values_list("notification_id", flat=True)
        )
        return Response(
            {
                "items": [notification_payload(n, unread=n.id not in read_ids) for n in items],
                "unreadCount": unread_for(request.tenant_context).count(),
            }
        )


class MessengerBindingListView(APIView):
    """Сервисные боты организации + статус привязки текущего сотрудника."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        bindings = {
            binding.integration_id: binding
            for binding in MessengerBinding.objects.filter(
                user=request.user,
                integration__organization=request.tenant_context.organization,
            )
        }
        messenger_types = preference_types(
            organization_id=request.tenant_context.organization_id,
            user_id=request.user.id,
            transport=NotificationTransport.MESSENGER,
        )
        items = []
        for integration in notifier_integrations(request.tenant_context):
            binding = bindings.get(integration.id)
            items.append(
                {
                    "integrationId": integration.id,
                    "provider": integration.provider,
                    "name": integration.name,
                    "botUsername": integration.config.get("bot_username", ""),
                    "bound": binding is not None,
                    "pushTypes": messenger_types if binding else [],
                }
            )
        # Реестр типов для чекбоксов в профиле (порядок — как в TYPE_META).
        available = [{"code": code, "label": t(meta["label"])} for code, meta in TYPE_META.items()]
        return Response({"items": items, "availableTypes": available})


class MessengerBindingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def _integration(self, request: Request, integration_id: int):
        return notifier_integrations(request.tenant_context).filter(id=integration_id).first()

    def post(self, request: Request, integration_id: int) -> Response:
        """Выдать одноразовый код привязки и deep-link на бота."""
        integration = self._integration(request, integration_id)
        if integration is None:
            return Response({"detail": t("profile.notification_bot_not_found")}, status=404)
        binding_code = issue_binding_code(
            context=request.tenant_context, integration=integration
        )
        return Response(
            {
                "code": binding_code.code,
                "deepLink": deep_link(integration, binding_code.code),
                "expiresAt": binding_code.expires_at.isoformat(),
            },
            status=201,
        )

    def patch(self, request: Request, integration_id: int) -> Response:
        """Обновить типы уведомлений, доставляемые в мессенджер."""
        binding = MessengerBinding.objects.filter(user=request.user, integration_id=integration_id).first()
        if binding is None:
            return Response({"detail": t("profile.link_not_found")}, status=404)
        types = request.data.get("pushTypes")
        if not isinstance(types, list):
            return Response({"detail": t("notifications.push_types_list")}, status=400)
        preference = update_preference(
            organization_id=request.tenant_context.organization_id,
            user_id=request.user.id,
            transport=NotificationTransport.MESSENGER,
            types=types,
        )
        return Response({"pushTypes": preference.types})

    def delete(self, request: Request, integration_id: int) -> Response:
        MessengerBinding.objects.filter(user=request.user, integration_id=integration_id).delete()
        # Отвязали бота — звать этим транспортом больше некуда.
        update_preference(
            organization_id=request.tenant_context.organization_id,
            user_id=request.user.id,
            transport=NotificationTransport.MESSENGER,
            enabled=False,
        )
        return Response({"ok": True})


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        conversation_id = request.data.get("conversationId")
        if request.data.get("all"):
            mark_read(context=request.tenant_context, all_unread=True)
        elif conversation_id is not None:
            # Сотрудник открыл диалог — окликать по нему больше нечем.
            if not isinstance(conversation_id, int) or isinstance(conversation_id, bool):
                return Response({"detail": t("notifications.conversation_id_number")}, status=400)
            mark_read(context=request.tenant_context, conversation_id=conversation_id)
        else:
            ids = request.data.get("ids")
            if not isinstance(ids, list):
                return Response({"detail": t("notifications.ids_list_or_all")}, status=400)
            mark_read(context=request.tenant_context, ids=[i for i in ids if isinstance(i, int)])
        return Response({"unreadCount": unread_for(request.tenant_context).count()})


class NotificationPreferenceView(APIView):
    """Настройка транспорта: включён ли он и о чём звать.

    Мессенджер настраивается через свою привязку (там же, где бот), браузеру
    отдельной сущности не нужно — разрешение живёт в самом браузере, а сюда
    попадает только намерение человека.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, transport: str) -> Response:
        if transport not in NotificationTransport.values:
            return Response({"detail": t("notifications.unknown_transport")}, status=404)
        preference = preference_for(
            organization_id=request.tenant_context.organization_id,
            user_id=request.user.id,
            transport=transport,
        )
        return Response(_preference_payload(preference))

    def patch(self, request: Request, transport: str) -> Response:
        if transport not in NotificationTransport.values:
            return Response({"detail": t("notifications.unknown_transport")}, status=404)
        types = request.data.get("types")
        if types is not None and not isinstance(types, list):
            return Response({"detail": t("notifications.push_types_list")}, status=400)
        enabled = request.data.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            return Response({"detail": t("notifications.enabled_bool")}, status=400)
        preference = update_preference(
            organization_id=request.tenant_context.organization_id,
            user_id=request.user.id,
            transport=transport,
            enabled=enabled,
            types=types,
        )
        return Response(_preference_payload(preference))


def _preference_payload(preference) -> dict:
    return {
        "transport": preference.transport,
        "enabled": preference.enabled,
        "types": list(preference.types or []),
        # Реестр типов — тот же, что у мессенджера: вопрос один на все транспорты.
        "availableTypes": [
            {"code": code, "label": t(meta["label"])} for code, meta in TYPE_META.items()
        ],
    }
