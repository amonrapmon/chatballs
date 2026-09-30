from django.db import models


class SystemEvent(models.TextChoices):
    """Код системного события диалога.

    Текст события раньше писался в ``text`` по-русски и оставался таким
    навсегда: история — записи, а не подписи, и перевести её задним числом
    нельзя. Поэтому в базу идёт код, а фразу собирает интерфейс на языке того,
    кто её читает. ``text`` продолжает заполняться: он остаётся и запасным
    вариантом для строк, записанных до этого поля, и тем, что видно в базе
    глазами.
    """

    OPERATOR_TOOK = "operator_took", "Оператор перехватил диалог"
    RETURNED_TO_AI = "returned_to_ai", "Диалог возвращён AI"
    RETURNED_TO_QUEUE = "returned_to_queue", "Диалог возвращён в очередь"
    AI_UNAVAILABLE = "ai_unavailable", "AI недоступен"
    AI_HANDED_OVER = "ai_handed_over", "AI передал диалог оператору"
    ASSIGNED_TO = "assigned_to", "Диалог назначен сотруднику"
    ASSIGNMENT_EXPIRED = "assignment_expired", "Назначение истекло"
    SITE_FIELDS_UPDATED = "site_fields_updated", "site_fields_updated"
    CALL_REQUESTED = "call_requested", "Запрошен звонок"
    CALL_ACCEPTED = "call_accepted", "Клиент принял приглашение"
    CALL_DECLINED = "call_declined", "Клиент отклонил приглашение"
    CALL_CANCELLED = "call_cancelled", "Приглашение отменено"
    CALL_MISSED = "call_missed", "Звонок пропущен"
    CALL_EXPIRED = "call_expired", "Приглашение истекло"
    CALL_STARTED = "call_started", "Звонок начался"
    CALL_ENDED = "call_ended", "Звонок завершён"
    CALL_FAILED = "call_failed", "Звонок не состоялся"
