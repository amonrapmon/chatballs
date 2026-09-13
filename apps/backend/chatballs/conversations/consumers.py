"""WebSocket оповещений рабочего места (см. chatballs.conversations.realtime и
chatballs.notifications.realtime).

Сокет один на сессию: по нему идут и события диалогов, и события уведомлений.
Второй сокет ради второго источника означал бы второе переподключение, вторую
аутентификацию и вторую точку отказа на ровном месте.

Правила:
- аутентификация — сессией того же SPA (AuthMiddlewareStack), отдельного токена
  нет: сокет открывает тот же браузер, что и REST;
- организация берётся из адреса, как и в HTTP-слое, и обязана совпадать с
  членством пользователя;
- подписка на диалог возможна только после проверки видимости — той же, что у
  REST (ADR-CHATBALLS-0043);
- события не содержат содержимого: клиент по ним перезапрашивает данные и
  получает ровно то, что ему позволено.
"""

from __future__ import annotations

import logging
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from chatballs.conversations.models import Conversation
from chatballs.conversations.realtime import conversation_group, inbox_group
from chatballs.conversations.selectors import conversation_is_visible
from chatballs.identity.models import OrganizationMembership
from chatballs.notifications.realtime import user_group
from chatballs.presence import touch
from chatballs.tenancy.database import tenant_atomic
from chatballs.tenancy.lookup import organization_by_public_id

logger = logging.getLogger(__name__)

NOT_A_MEMBER_CLOSE = 4403


class ConversationEventsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self) -> None:
        self.organization_id: int | None = None
        self.membership_id: int | None = None
        self.watched: str | None = None
        self.personal: str | None = None
        self.user_id: int | None = None
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close(code=NOT_A_MEMBER_CLOSE)
            return
        raw_public_id = self.scope["url_route"]["kwargs"]["organization_public_id"]
        resolved = await self._membership(user.id, raw_public_id)
        if resolved is None:
            await self.close(code=NOT_A_MEMBER_CLOSE)
            return
        self.organization_id, self.membership_id = resolved
        self.user_id = user.id
        # Открытый сокет и есть присутствие: ничего специально «включать» для
        # этого сотрудник не должен (chatballs.presence).
        await self._touch_presence()
        await self.channel_layer.group_add(inbox_group(self.organization_id), self.channel_name)
        # Уведомления адресованы человеку, а не организации: у каждого своя группа.
        self.personal = user_group(user.id)
        await self.channel_layer.group_add(self.personal, self.channel_name)
        await self.accept()

    async def disconnect(self, code: int) -> None:
        if self.organization_id is not None and self.user_id is not None:
            # Не «его нет», а «здесь он был в последний раз».
            await database_sync_to_async(touch)(self.organization_id, self.user_id)
        if self.organization_id is not None:
            await self.channel_layer.group_discard(
                inbox_group(self.organization_id), self.channel_name
            )
        if self.personal is not None:
            await self.channel_layer.group_discard(self.personal, self.channel_name)
        if self.watched is not None:
            await self.channel_layer.group_discard(self.watched, self.channel_name)

    async def receive_json(self, content: dict, **kwargs) -> None:
        """Клиент сообщает, какой диалог открыт: событий по нему он и ждёт.

        Он же раз в минуту присылает heartbeat — по нему продлевается отметка
        присутствия. Без неё ключ истекает сам, и оборванное соединение
        перестаёт считаться живым без отдельного уборщика.
        """
        if self.organization_id is None:
            return
        if content.get("type") == "ping":
            await self._touch_presence()
            return
        if content.get("type") != "watch":
            return
        conversation_id = content.get("conversationId")
        if self.watched is not None:
            await self.channel_layer.group_discard(self.watched, self.channel_name)
            self.watched = None
        if not isinstance(conversation_id, int):
            return
        if not await self._may_watch(conversation_id):
            # Молча: отсутствие подписки и отсутствие прав снаружи неразличимы.
            return
        self.watched = conversation_group(conversation_id)
        await self.channel_layer.group_add(self.watched, self.channel_name)
        # Подтверждение — не вежливость: пока его нет, события диалога ещё могут
        # пройти мимо, и клиенту после переподключения нужно знать, с какого
        # момента лента снова живая.
        await self.send_json({"type": "watching", "conversationId": conversation_id})

    async def fanout(self, event: dict) -> None:
        await self.send_json(event["payload"])

    async def _touch_presence(self) -> None:
        if self.organization_id is None or self.user_id is None:
            return
        await database_sync_to_async(touch)(self.organization_id, self.user_id)

    @database_sync_to_async
    def _membership(self, user_id: int, raw_public_id: str) -> tuple[int, int] | None:
        try:
            organization = organization_by_public_id(uuid.UUID(str(raw_public_id)))
        except ValueError:
            return None
        if organization is None:
            return None
        with tenant_atomic(organization.pk):
            membership = (
                OrganizationMembership.objects.select_related("user")
                .filter(
                    organization_id=organization.pk,
                    user_id=user_id,
                    blocked_at__isnull=True,
                    user__is_active=True,
                )
                .first()
            )
        if membership is None:
            return None
        return organization.pk, membership.pk

    @database_sync_to_async
    def _may_watch(self, conversation_id: int) -> bool:
        with tenant_atomic(self.organization_id):
            membership = (
                OrganizationMembership.objects.select_related("user")
                .filter(pk=self.membership_id)
                .first()
            )
            conversation = Conversation.objects.filter(
                id=conversation_id, organization_id=self.organization_id
            ).first()
            if membership is None or conversation is None:
                return False
            return conversation_is_visible(actor=membership, conversation=conversation)
