"""Что происходит, когда диалог ждёт слишком долго.

Раньше не происходило ничего. Про ждущий диалог операторов окликали ровно один
раз, и дальше `dedup_key` на сутки гарантировал тишину: если в тот момент никто
не смотрел на экран, диалог мог провисеть до автозакрытия, и узнать об этом было
неоткуда.

Уровень выбирается по времени ожидания, а не по счётчику попыток: состояние
хранить не нужно, потому что повтор гасит тот же `dedup_key` — свой у каждого
уровня. Свип идеемпотентен и может выполняться сколь угодно часто.

Назначенный диалог не эскалируется: он не в общей очереди, а в личной, и у неё
свой срок — не взял, значит возвращаем всем. Возвращает его не обход, а правило
обработки (conversations.rules.assignment_return): срок ставится в момент
назначения. Обход только сверяет, что срок поставлен, — на случай назначений,
сделанных до появления правил или пока правило было выключено.

Присутствие сокращает ожидание, но не заменяет его. Если в группе диалога сейчас
никого нет за рабочим местом, ждать второго порога бессмысленно: напоминать
некому, и круг расширяется сразу. Обратного правила нет — присутствие никого не
задерживает и ничего не запрещает, потому что ошибается в обе стороны.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from chatballs.conversations.models import ControlMode, Conversation, LifecycleState
from chatballs.conversations.queue_models import QueueEscalationPolicy, policy_for
from chatballs.conversations.rules.assignment_return import reconcile
from chatballs.i18n import t
from chatballs.notifications.models import (
    NotificationAudience,
    NotificationLevel,
    NotificationType,
)
from chatballs.notifications.recipients import audience_user_ids
from chatballs.notifications.services import notify, notify_management
from chatballs.presence import online_user_ids
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


def _contact_name(conversation: Conversation) -> str:
    return getattr(conversation.contact, "name", "") or t("conversations.guest")


def _waiting_conversations(context: TenantContext):
    return Conversation.objects.filter(
        organization=context.organization,
        lifecycle=LifecycleState.OPEN,
        control_mode=ControlMode.PAUSED,
        waiting_since__isnull=False,
    ).select_related("contact", "assigned_operator", "group")


def sweep_waiting_conversations(context: TenantContext) -> int:
    """Оклики по ждущим диалогам организации. Возвращает число новых уведомлений."""
    with tenant_atomic(context):
        policy = policy_for(context.organization)
        now = timezone.now()
        fired = 0
        for conversation in _waiting_conversations(context).select_for_update(of=("self",)):
            if conversation.assigned_operator_id:
                reconcile(conversation)
            else:
                fired += _escalate(context, conversation, policy, now)
        return fired


def _nobody_is_watching(context: TenantContext, conversation: Conversation) -> bool:
    """В группе диалога никого нет за рабочим местом."""
    watchers = audience_user_ids(
        organization_id=context.organization_id,
        audience=NotificationAudience.OPERATORS,
        group_id=conversation.group_id,
    )
    return not online_user_ids(context.organization_id, watchers)


def _escalate(
    context: TenantContext,
    conversation: Conversation,
    policy: QueueEscalationPolicy,
    now: datetime,
) -> int:
    waited = now - conversation.waiting_since
    contact = _contact_name(conversation)
    common = {
        "context": context,
        "type": NotificationType.DIALOG_WAITING_LONG,
        "text_params": {"contact": contact},
        "target_id": conversation.id,
        "source_type": "Conversation",
        "source_id": conversation.id,
    }
    fired = 0
    if waited >= timedelta(minutes=policy.remind_after_minutes):
        # Тот же круг, что и в первый раз: смена на месте, просто не заметила.
        fired += notify(
            audience=NotificationAudience.OPERATORS,
            audience_group=conversation.group,
            level=NotificationLevel.WARNING,
            title=f"Диалог всё ещё ждёт · {contact}",
            title_key="notifications.still_waiting",
            body_key="notifications.still_waiting_body",
            dedup_key=f"waiting:{conversation.id}:remind",
            **common,
        ) is not None
    widen_after = policy.widen_after_minutes
    if waited >= timedelta(minutes=policy.remind_after_minutes) and _nobody_is_watching(
        context, conversation
    ):
        # Некому заметить напоминание — второй порог ждать незачем.
        widen_after = min(widen_after, policy.remind_after_minutes)
    if waited >= timedelta(minutes=widen_after):
        # Круг шире группы: в своей группе ответить некому.
        fired += notify(
            audience=NotificationAudience.OPERATORS,
            audience_group=None,
            level=NotificationLevel.WARNING,
            title=f"Диалог всё ещё ждёт · {contact}",
            title_key="notifications.still_waiting",
            body_key="notifications.still_waiting_body",
            dedup_key=f"waiting:{conversation.id}:widen",
            **common,
        ) is not None
    if waited >= timedelta(minutes=policy.escalate_after_minutes):
        # Это уже не про сменщика, а про то, что смены нет.
        fired += notify_management(
            level=NotificationLevel.CRITICAL,
            title=f"Диалог никто не берёт · {contact}",
            title_key="notifications.waiting_unattended",
            body_key="notifications.waiting_unattended_body",
            dedup_key=f"waiting:{conversation.id}:management",
            **common,
        )
    return fired
