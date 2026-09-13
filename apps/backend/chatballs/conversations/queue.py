"""Очередь к оператору: единственное место, где диалог в неё входит и выходит.

Правило «диалог ждёт человека» — это три поля сразу: control_mode = PAUSED,
expected_responder = OPERATOR и момент, с которого пошло ожидание. Раньше первые
два выставлялись в шести местах подряд (создание диалога без доступного AI,
клиент написал в диалог без AI, голосовое без расшифровки, сбой провайдера,
хендофф агента, ручной возврат оператором), а третьего не было вовсе: «дольше
всех ждущий» считался по времени последнего сообщения.

Из-за этого очередь вела себя обратно смыслу. Клиент, который писал повторно,
двигал last_message_at вперёд и падал в конец очереди: чем настойчивее человек,
тем позже до него доходили руки. Поэтому waiting_since ставится один раз — при
входе в очередь — и не обновляется, пока диалог из неё не вышел.
"""

from __future__ import annotations

from datetime import datetime

from django.utils import timezone

from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    ExpectedResponder,
    LifecycleState,
)

# Что пишет enter_queue. Вызывающий кладёт это в update_fields своего save():
# состояние диалога меняется вместе с остальными полями, одной записью.
QUEUE_FIELDS = ("control_mode", "expected_responder", "waiting_since")


def is_waiting(conversation: Conversation) -> bool:
    """Диалог стоит в очереди к человеку.

    Закрытый и спам тоже лежат в PAUSED, но никого не ждут — отсюда проверка
    жизненного цикла.
    """
    return (
        conversation.lifecycle == LifecycleState.OPEN
        and conversation.control_mode == ControlMode.PAUSED
    )


def enter_queue(conversation: Conversation, *, now: datetime | None = None) -> bool:
    """Ставит диалог в очередь. True — если он в неё только что попал.

    Возврат нужен вызывающему, чтобы решить, звать ли операторов: повторное
    сообщение клиента в уже ждущий диалог очередь не меняет и второго оклика не
    заслуживает.
    """
    entered = not is_waiting(conversation)
    conversation.control_mode = ControlMode.PAUSED
    conversation.expected_responder = ExpectedResponder.OPERATOR
    if entered:
        conversation.waiting_since = now or timezone.now()
    return entered


def leave_queue(conversation: Conversation) -> None:
    """Диалог больше никого не ждёт.

    Несимметрично enter_queue намеренно: вход в очередь — одно состояние, а
    выходов несколько (оператор взял, диалог вернули AI, закрыли, пометили
    спамом), и control_mode у каждого свой. Общее у них только одно — ожидание
    закончилось, и его начало больше не имеет смысла.
    """
    conversation.waiting_since = None
