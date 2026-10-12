from datetime import UTC, datetime

from django.db.models import (
    Case,
    DateTimeField,
    F,
    IntegerField,
    Q,
    QuerySet,
    Value,
    When,
)
from django.db.models.functions import Coalesce

from chatballs.api.pagination import SortKey
from chatballs.conversations.access import visibility_predicate
from chatballs.conversations.audience import ConversationAudience
from chatballs.conversations.history_selectors import conversation_records
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    LifecycleState,
    Message,
)
from chatballs.identity.policy import conversation_visibility
from chatballs.tenancy.context import TenantContext


def conversations_for_context(context: TenantContext) -> QuerySet[Conversation]:
    return (
        Conversation.objects.filter(organization_id=context.organization_id)
        .select_related(
            "channel",
            "contact",
            "connection",
            "assigned_operator",
            "group",
        )
        .prefetch_related("labels")
        # Инбокс сортируется по времени последнего сообщения (а не по служебной
        # активности вроде claim/takeover). Поле денормализовано и держится
        # сигналом: агрегат max(messages.created_at) не ложился ни в индекс, ни
        # в курсор окна — на каждый запрос выходил GROUP BY по всей ленте.
        .order_by("-last_message_at", "-id")
    )


# Ключи сортировки инбокса. Порядок и правило сравнения курсора — одно и то же
# знание, поэтому оно живёт здесь, а не разъезжается по view.
ACTIVITY_KEYS = (SortKey("last_message_at"), SortKey("id"))
WAITING_KEYS = (
    SortKey("_waiting_rank", descending=False),
    SortKey("_wait_at", descending=False),
    SortKey("last_message_at"),
    SortKey("id"),
)
# Заглушка ключа ожидания для диалогов, которые человека не ждут: ключ окна
# обязан быть непустым, а эти строки всё равно упорядочены следующим ключом.
_NOT_WAITING_AT = datetime(1970, 1, 1, tzinfo=UTC)


def order_conversations(
    queryset: QuerySet[Conversation], sort: str
) -> tuple[QuerySet[Conversation], tuple[SortKey, ...]]:
    """Порядок инбокса и ключи его курсора.

    Сортировка живёт на сервере вместе с окном: клиент видит не весь набор, и
    переставлять в браузере ему нечего. `waiting` — «ждущие человека первыми,
    дольше всех ждущий выше», остальные — по убыванию активности.

    «Дольше всех ждущий» считается от waiting_since — момента, когда диалог
    встал в очередь. По времени последнего сообщения его считать нельзя: клиент,
    написавший повторно, двигал бы себя в конец очереди, и чем настойчивее он
    напоминал о себе, тем позже до него доходила очередь.
    """
    if sort != "waiting":
        return queryset.order_by("-last_message_at", "-id"), ACTIVITY_KEYS
    waits = Q(lifecycle=LifecycleState.OPEN, control_mode=ControlMode.PAUSED)
    ordered = queryset.annotate(
        _waiting_rank=Case(
            When(waits, then=Value(0)), default=Value(1), output_field=IntegerField()
        ),
        _wait_at=Case(
            # Coalesce — страховка для строк, встававших в очередь до появления
            # waiting_since: без неё они ушли бы в конец очереди вместо начала.
            When(waits, then=Coalesce(F("waiting_since"), F("last_message_at"))),
            default=Value(_NOT_WAITING_AT),
            output_field=DateTimeField(),
        ),
    ).order_by("_waiting_rank", "_wait_at", "-last_message_at", "-id")
    return ordered, WAITING_KEYS


def conversation_messages(conversation: Conversation) -> QuerySet[Message]:
    """Лента сообщений диалога. Окно и направление задаёт вызывающий."""
    return conversation_records(conversation, audience=ConversationAudience.PUBLIC)


# История читается в двух направлениях: вверх по ленте (от свежих к старым —
# открытие диалога и подгрузка при прокрутке) и вперёд от последнего известного
# сообщения (дельта обновления).
MESSAGES_OLDER_KEYS = (SortKey("created_at"), SortKey("id"))
MESSAGES_NEWER_KEYS = (
    SortKey("created_at", descending=False),
    SortKey("id", descending=False),
)


def apply_conversation_visibility(
    queryset: QuerySet[Conversation], context: TenantContext
) -> QuerySet[Conversation]:
    """Рабочая видимость и явная область контроля супервизора (ADR-0033)."""
    if context.membership is None or context.membership.organization_id != context.organization_id:
        return queryset.none()
    queryset = queryset.filter(organization_id=context.organization_id)
    scope = conversation_visibility(context.membership)
    if scope is None:
        return queryset
    if scope.get("none"):
        return queryset.none()
    return queryset.filter(visibility_predicate(scope)).distinct()


def conversation_is_visible(*, actor, conversation: Conversation) -> bool:
    """Точечная проверка той же видимости для уже загруженного диалога."""
    from chatballs.identity.policy import require_capability

    return require_capability(actor, "conversations.view", conversation)


def visible_conversations_for(context: TenantContext) -> QuerySet[Conversation]:
    return apply_conversation_visibility(conversations_for_context(context), context)


def conversation_for_context(*, context: TenantContext, conversation_id: int) -> Conversation:
    return visible_conversations_for(context).get(id=conversation_id)
