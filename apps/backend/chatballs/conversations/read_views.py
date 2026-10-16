from django.db.models import Exists, OuterRef
from rest_framework.request import Request
from rest_framework.response import Response

from chatballs.api.pagination import (
    cursor_id,
    window,
    window_payload,
    window_size,
)
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    ConversationRead,
    LifecycleState,
    Message,
)
from chatballs.conversations.participant_access_loss import access_loss_payload
from chatballs.conversations.participant_models import ConversationParticipant
from chatballs.conversations.selectors import (
    order_conversations,
    visible_conversations_for,
)
from chatballs.conversations.serializers import (
    conversation_payload,
    last_messages_for,
    pending_counts_for,
)
from chatballs.conversations.services import (
    delete_conversation,
)
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t
from chatballs.identity.policy import can_administer_access
from chatballs.native_mirror.visibility import visible_messages

# Окно инбокса и окно истории: размеры продуктовые, клиент может запросить
# меньше, больше — только до потолка api.pagination.
LIST_WINDOW_SIZE = 30


class ConversationListView(ConversationViewBase):
    def get(self, request: Request) -> Response:
        from django.db.models import Q

        params = request.query_params
        items = visible_conversations_for(request.tenant_context)
        # «Удалённые» (архив) скрыты; просмотр архива — только администратор.
        if params.get("archived") == "1":
            if not can_administer_access(request.tenant_context.membership):
                return Response({"detail": t("conversations.archive_admin_only")}, status=403)
            items = items.filter(archived_at__isnull=False)
        else:
            items = items.filter(archived_at__isnull=True)
        group = params.get("group")
        if group == "none":
            items = items.filter(group__isnull=True)
        elif group:
            items = items.filter(group_id=group)
        agent = params.get("agent")
        if agent:
            items = items.filter(channel_id=agent)
        lifecycle = params.get("lifecycle")
        if lifecycle:
            items = items.filter(lifecycle=lifecycle)
        else:
            # Спам не показывается в обычных вкладках (дизайн-базлайн v2).
            items = items.exclude(lifecycle=LifecycleState.SPAM)
        assigned = params.get("assigned")
        if assigned == "me":
            items = items.filter(assigned_operator_id=request.user.id)
        elif assigned and assigned.isdigit():
            # Охват «Ответственный» в поповере админа (дизайн-базлайн v2, A1).
            items = items.filter(assigned_operator_id=int(assigned))
        if params.get("waiting") == "1":
            items = items.filter(
                lifecycle=LifecycleState.OPEN, control_mode=ControlMode.PAUSED
            )
        # Две вкладки ожидания (макет «Очередь и уведомления», кадр Q3): общая
        # очередь — диалоги без ответственного, их берёт кто угодно; «на мне» —
        # назначенные лично и ждущие, пока их возьмут.
        if params.get("queue") == "1":
            items = items.filter(
                lifecycle=LifecycleState.OPEN,
                control_mode=ControlMode.PAUSED,
                assigned_operator__isnull=True,
            )
        if params.get("waitingOnMe") == "1":
            items = items.filter(
                lifecycle=LifecycleState.OPEN,
                control_mode=ControlMode.PAUSED,
                assigned_operator_id=request.user.id,
            )
        query = params.get("q", "").strip()
        if query:
            from django.contrib.postgres.search import SearchQuery, SearchVector

            # Имена — по подстроке; тексты сообщений — полнотекстовым поиском
            # (russian-конфиг, GIN-индекс conv_message_text_fts). Конфигурация
            # одна на оба языка и от языка организации не зависит: в «russian»
            # латиница отдана english_stem, а кириллица — russian_stem, так что
            # английская переписка стеммится английским стеммером. Менять её на
            # «english» нельзя — та оставит без основы русские слова.
            search = SearchQuery(query, config="russian", search_type="websearch")
            message_match = (
                visible_messages(Message.objects.filter(conversation=OuterRef("pk")))
                .annotate(fts=SearchVector("text", config="russian"))
                .filter(fts=search)
            )
            items = items.filter(
                Q(contact__name__icontains=query)
                | Q(Exists(message_match))
            )
        # Инбокс — живая лента: окно по курсору, а не номера страниц. Сортировка
        # серверная, иначе окно и порядок разъезжаются.
        items = items.annotate(viewer_participates=Exists(ConversationParticipant.objects.active().filter(
            organization_id=request.tenant_context.organization_id,
            conversation_id=OuterRef("pk"), membership_id=request.tenant_context.membership.pk,
        )))
        ordered, keys = order_conversations(items, params.get("sort", "activity"))
        page = window(
            ordered,
            keys=keys,
            limit=window_size(params, default=LIST_WINDOW_SIZE),
            after=cursor_id(params),
        )
        # Отметки прочтения просматривающего: бейдж считается персонально.
        read_map = dict(
            ConversationRead.objects.filter(
                user=request.user, conversation__in=page.items
            ).values_list("conversation_id", "last_read_message_id")
        )
        # Превью и бейдж — на всю страницу разом: построчно это давало по два
        # запроса на диалог при обновлении списка раз в четыре секунды.
        conversation_ids = [conversation.id for conversation in page.items]
        previews = last_messages_for(conversation_ids)
        pending = pending_counts_for(conversation_ids, read_map)
        return Response(
            window_payload(
                page,
                lambda c: conversation_payload(
                    c,
                    last_read_id=read_map.get(c.id, 0),
                    viewer_id=request.user.id,
                    last_message=previews.get(c.id),
                    pending_count=pending.get(c.id, 0),
                ),
                # Счётчик над списком показывает весь охват с учётом фильтров,
                # а не число уже загруженных строк.
                total=ordered.order_by().count(),
            )
        )


class ConversationDetailView(ConversationViewBase):
    def get(self, request: Request, conversation_id: int) -> Response:
        try:
            conversation = self._conversation(request, conversation_id)
        except Conversation.DoesNotExist:
            return Response(access_loss_payload(request.tenant_context, conversation_id), status=404)
        # Открытие диалога = прочтение: двигаем персональную отметку до последнего
        # сообщения (detail поллится каждые 3 с — пишем только при продвижении).
        last_id = conversation.messages.order_by("-id").values_list("id", flat=True).first() or 0
        if last_id:
            read, created = ConversationRead.objects.get_or_create(
                conversation=conversation, user=request.user, defaults={"last_read_message_id": last_id}
            )
            if not created and read.last_read_message_id < last_id:
                read.last_read_message_id = last_id
                read.save(update_fields=["last_read_message_id", "updated_at"])
        return Response(
            {
                "conversation": conversation_payload(
                    conversation,
                    detailed=True,
                    viewer_id=request.user.id,
                )
            }
        )

    def delete(self, request: Request, conversation_id: int) -> Response:
        """Удалить диалог вместе с перепиской — насовсем.

        Право есть только у владельца и администратора: оператор закрывает
        диалог и помечает спам, но не стирает историю организации.
        """
        try:
            conversation = self._conversation(
                request, conversation_id, "conversations.operate"
            )
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        if not can_administer_access(request.tenant_context.membership):
            return Response(
                {"detail": t("conversations.delete_admin_only")}, status=403
            )
        # Запись журнала — до удаления: после него у диалога уже нет ни строки,
        # ни идентификатора, который можно было бы записать.
        self._audit(request, "deleted", conversation)
        delete_conversation(context=request.tenant_context, conversation=conversation)
        return Response(status=204)
