from django.conf import settings
from django.db import models

from chatballs.tenancy.models import TenantRelationModel

# Уведомления: событие создаётся один раз и адресуется аудитории; прочтение —
# персональное (NotificationRead). Фундамент под любые типы событий, не только чат.


class NotificationType(models.TextChoices):
    """Что произошло. Набор — из макета «Очередь и уведомления», фрейм Q1.

    Это ровно тот список, который сотрудник видит галочками в профиле, поэтому
    типы разделены по смыслу для человека, а не по месту в коде. «Клиент
    запросил оператора» и «диалог долго ждёт» раньше были одним типом, и
    отписаться от второго, не потеряв первое, было нельзя.

    «Новый диалог» стоит отдельно от «клиент запросил оператора» по той же
    причине: диалог может начаться и на канале с работающим агентом, где
    человека никто не звал, и называть такой оклик просьбой о человеке — врать.
    """

    NEW_DIALOG = "NEW_DIALOG", "Новый диалог"
    OPERATOR_REQUESTED = "OPERATOR_REQUESTED", "Клиент запросил оператора"
    DIALOG_NEW_MESSAGE = "DIALOG_NEW_MESSAGE", "Новое сообщение в моём диалоге"
    DIALOG_ASSIGNED = "DIALOG_ASSIGNED", "Диалог назначили на меня"
    DIALOG_WAITING_LONG = "DIALOG_WAITING_LONG", "Диалог долго ждёт человека"
    AI_STOPPED = "AI_STOPPED", "AI остановлен ошибкой или лимитом"


class NotificationLevel(models.TextChoices):
    INFO = "INFO", "Инфо"
    SUCCESS = "SUCCESS", "Успех"
    WARNING = "WARNING", "Предупреждение"
    CRITICAL = "CRITICAL", "Критично"


class NotificationAudience(models.TextChoices):
    ALL = "ALL", "Все"
    OWNER = "OWNER", "Владелец"
    OPERATORS = "OPERATORS", "Операторы"
    USER = "USER", "Конкретный пользователь"


class Notification(models.Model):
    organization = models.ForeignKey("identity.Organization", on_delete=models.PROTECT, related_name="notifications")
    type = models.CharField(max_length=32, choices=NotificationType.choices)
    level = models.CharField(max_length=16, choices=NotificationLevel.choices, default=NotificationLevel.INFO)
    # Текст на языке того, кто писал код: остаётся и для записей, сделанных
    # до появления ключей, и для доставки в мессенджер, где рендерить нечем.
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    # Ключи каталога и их параметры. Уведомление адресовано аудитории
    # («операторам»), а не одному человеку, и разные операторы могут читать на
    # разных языках — поэтому фраза собирается при показе, а не при записи.
    title_key = models.CharField(max_length=64, blank=True, default="")
    body_key = models.CharField(max_length=64, blank=True, default="")
    text_params = models.JSONField(default=dict, blank=True)
    # Диплинк по клику.
    target_route = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    audience = models.CharField(max_length=16, choices=NotificationAudience.choices, default=NotificationAudience.ALL)
    # Граница видимости уведомления (ADR-CHATBALLS-0043 §4). Уведомление о диалоге
    # видно тем же, кому виден сам диалог: иначе оператор чужой группы получает
    # оклик с именем клиента и куском переписки, а открыть диалог не может.
    # NULL — видно всем, кого пропускает аудитория.
    audience_group = models.ForeignKey(
        "identity.EmployeeGroup",
        on_delete=models.SET_NULL,
        related_name="notifications",
        null=True,
        blank=True,
    )
    recipient_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="direct_notifications")
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    dedup_key = models.CharField(max_length=128, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "created_at"])]

    def __str__(self) -> str:
        return f"notif:{self.type}/{self.audience}"


class NotificationRead(TenantRelationModel):
    tenant_relation_fields = ("notification",)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="reads")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_reads")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["notification", "user"], name="uniq_notification_read")]


def default_push_types() -> list[str]:
    # Дефолт — то, что касается лично и требует действия: позвали человека,
    # написали в мой диалог, назначили на меня. «Долго ждёт» и сбой AI —
    # подписка по желанию, иначе оклик обесценивается.
    # «Новый диалог» сюда не входит: диалог, которым занимается агент, лично
    # никого не касается. Кому он нужен — включит галочкой.
    return [
        NotificationType.OPERATOR_REQUESTED,
        NotificationType.DIALOG_NEW_MESSAGE,
        NotificationType.DIALOG_ASSIGNED,
    ]


class NotificationTransport(models.TextChoices):
    BROWSER = "BROWSER", "Браузер"
    MESSENGER = "MESSENGER", "Мессенджер"


class NotificationPreference(models.Model):
    """Куда и о чём окликать сотрудника.

    Одна настройка на все транспорты. Браузер и бот в мессенджере отвечают на
    один и тот же вопрос — «о чём меня звать», — и второй такой же список
    галочек в профиле означал бы два расходящихся ответа на него. Новый
    транспорт (почта, мобильное приложение) — это строка здесь, а не ещё одна
    таблица настроек.

    Разрешение самого браузера тут не хранится: оно живёт в браузере, своё на
    каждом устройстве, и сервер его ни выдать, ни отозвать не может. Здесь
    только намерение человека — хочет ли он, чтобы его окликали.
    """

    organization = models.ForeignKey(
        "identity.Organization", on_delete=models.PROTECT, related_name="notification_preferences"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences"
    )
    transport = models.CharField(max_length=16, choices=NotificationTransport.choices)
    enabled = models.BooleanField(default=False)
    # Подмножество NotificationType; пустой список — не звать вовсе.
    types = models.JSONField(default=default_push_types, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user", "transport"], name="uniq_notification_preference"
            )
        ]

    def __str__(self) -> str:
        return f"pref:{self.user_id}/{self.transport}"


class MessengerBinding(TenantRelationModel):
    """Привязка сотрудника к сервисному боту уведомлений (TG/MAX).

    Создаётся при подтверждении одноразового кода из профиля; уведомления
    доставляются в external_chat_id через транспорт интеграции."""

    tenant_relation_fields = ("integration",)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="messenger_bindings")
    integration = models.ForeignKey("integrations.Integration", on_delete=models.CASCADE, related_name="messenger_bindings")
    external_chat_id = models.CharField(max_length=128)
    # Типы событий живут не здесь, а в NotificationPreference: вопрос «о чём
    # звать» один на все транспорты, и ответ на него обязан быть один.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["integration", "user"], name="uniq_binding_integration_user")]

    def __str__(self) -> str:
        return f"binding:{self.user_id}/{self.integration_id}"


class MessengerBindingCode(TenantRelationModel):
    tenant_relation_fields = ("integration",)
    # Одноразовый код привязки (deep-link ?start=<code>); TTL ~10 минут.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="messenger_binding_codes")
    integration = models.ForeignKey("integrations.Integration", on_delete=models.CASCADE, related_name="messenger_binding_codes")
    code = models.CharField(max_length=32, unique=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"binding-code:{self.user_id}/{self.integration_id}"
