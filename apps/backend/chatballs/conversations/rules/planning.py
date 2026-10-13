"""Доменный факт диалога как повод поставить или снять действие правила.

Факты пишутся в одном месте (conversations.domain_events), поэтому и правила
узнают о них в одном месте — в той же транзакции и под той же блокировкой
диалога. Отдельного обхода, который догадывался бы о назначении по времени,
для этого не нужно.
"""

from __future__ import annotations

from chatballs.conversations.rules import assignment_return


def fact_recorded(conversation, event) -> None:
    """`conversation` — заблокированная строка с состоянием на момент факта."""
    if event.event_type in assignment_return.RELEVANT_FACTS:
        assignment_return.reconcile(conversation)
