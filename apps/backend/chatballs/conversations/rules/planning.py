"""Доменный факт диалога как повод поставить или снять действие правила.

Факты пишутся в одном месте (conversations.domain_events), поэтому и правила
узнают о них в одном месте — в той же транзакции и под той же блокировкой
диалога. Отдельного обхода, который догадывался бы о назначении по времени,
для этого не нужно.

Сообщение клиента фактом не является, но ожидание ответа начинает именно оно,
поэтому приём сообщает о нём отдельно.
"""

from __future__ import annotations

from chatballs.conversations.models import ControlMode
from chatballs.conversations.rules import (
    assignment_return,
    receipt_confirmation,
    reply_reminder,
    wait_notice,
)

_BY_FACT = (assignment_return, receipt_confirmation, wait_notice, reply_reminder)


def fact_recorded(conversation, event) -> None:
    """`conversation` — заблокированная строка с состоянием на момент факта."""
    for rule in _BY_FACT:
        if event.event_type in rule.RELEVANT_FACTS:
            rule.reconcile(conversation)


def customer_message_received(conversation) -> None:
    """Клиент написал. `conversation` — заблокированная строка диалога."""
    if conversation.control_mode == ControlMode.HUMAN:
        reply_reminder.reconcile(conversation)
