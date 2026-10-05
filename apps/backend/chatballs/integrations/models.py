from django.db import models

from chatballs.identity.crypto import EncryptedCharField

# Интеграции: провайдеры (LLM) и подключения (боты/виджеты). ADR-CHATBALLS-0020.
# Привязка подключения к каналу обработки появляется в M1.


class IntegrationKind(models.TextChoices):
    LLM_PROVIDER = "LLM_PROVIDER", "LLM-провайдер"
    MESSENGER = "MESSENGER", "Подключение-мессенджер"
    # Внешний сервер: откуда агент берёт данные организации (SPEC-0023 R-1).
    EXTERNAL_SERVER = "EXTERNAL_SERVER", "Внешний сервер"


class IntegrationProvider(models.TextChoices):
    OPENROUTER = "OPENROUTER", "OpenRouter"
    CUSTOM = "CUSTOM", "Custom (OpenAI-compatible)"
    # Демо-провайдер: живой AI без ключей и сети — для знакомства с системой.
    DEMO = "DEMO", "Демо-провайдер (без ключа)"
    MAX = "MAX", "MAX"
    TELEGRAM = "TELEGRAM", "Telegram"
    VK = "VK", "ВКонтакте"
    WEB = "WEB", "Web-виджет"
    EMAIL = "EMAIL", "Email (IMAP/SMTP)"
    # Виды внешнего сервера: MCP-сервер с набором инструментов и HTTP-запрос —
    # один инструмент поверх REST API организации.
    MCP = "MCP", "MCP-сервер"
    HTTP = "HTTP", "HTTP-запрос"


class IntegrationStatus(models.TextChoices):
    UNCHECKED = "UNCHECKED", "Не проверено"
    OK = "OK", "Подключено"
    ERROR = "ERROR", "Ошибка"


# Какой провайдер к какому роду относится.
PROVIDER_KIND = {
    IntegrationProvider.OPENROUTER: IntegrationKind.LLM_PROVIDER,
    # Custom — generic BYOK для любого OpenAI-compatible endpoint (ADR-CHATBALLS-0034).
    IntegrationProvider.CUSTOM: IntegrationKind.LLM_PROVIDER,
    IntegrationProvider.DEMO: IntegrationKind.LLM_PROVIDER,
    IntegrationProvider.MAX: IntegrationKind.MESSENGER,
    IntegrationProvider.TELEGRAM: IntegrationKind.MESSENGER,
    # Сообщество ВКонтакте: приём через Bots Long Poll, отправка messages.send.
    IntegrationProvider.VK: IntegrationKind.MESSENGER,
    IntegrationProvider.WEB: IntegrationKind.MESSENGER,
    # Email-ящик — транспорт диалогов наравне с ботами (ADR-CHATBALLS-0035).
    IntegrationProvider.EMAIL: IntegrationKind.MESSENGER,
    IntegrationProvider.MCP: IntegrationKind.EXTERNAL_SERVER,
    IntegrationProvider.HTTP: IntegrationKind.EXTERNAL_SERVER,
}


class Integration(models.Model):
    organization = models.ForeignKey("identity.Organization", on_delete=models.PROTECT, related_name="integrations")
    kind = models.CharField(max_length=16, choices=IntegrationKind.choices)
    provider = models.CharField(max_length=16, choices=IntegrationProvider.choices)
    name = models.CharField(max_length=255)
    # Зашифрованный секрет: ключ провайдера или токен бота (Fernet).
    secret = EncryptedCharField(max_length=1024, blank=True)
    # Секретные заголовки внешнего сервера: JSON «имя → значение» (Fernet).
    # Имена и открытые заголовки лежат в config, наружу значения не отдаются.
    secret_headers = EncryptedCharField(max_length=16384, blank=True)
    # Несекретная конфигурация: base_url, модель по умолчанию и т.п.
    config = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=IntegrationStatus.choices, default=IntegrationStatus.UNCHECKED)
    # Операционное состояние подключения. В отличие от status (результата
    # последней проверки), is_active явно разрешает или запрещает runtime.
    is_active = models.BooleanField(default=True)
    # Что разрешено в этой точке входа (админ, «Настройки → Голосовые и звонки»):
    # голосовые сообщения (запись в композере/виджете) и онлайн-звонки.
    voice_messages_enabled = models.BooleanField(default=True)
    audio_calls_enabled = models.BooleanField(default=True)
    video_calls_enabled = models.BooleanField(default=True)
    # Подключение (бот/виджет) привязано к каналу обработки.
    channel = models.ForeignKey("channels.Channel", on_delete=models.SET_NULL, null=True, blank=True, related_name="connections")
    # Курсор Long Polling (marker MAX / offset Telegram).
    poll_marker = models.CharField(max_length=64, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    # Код причины последней ошибки внешнего сервера: по нему интерфейс выбирает
    # состояние (недоступен, неверная авторизация, адрес запрещён).
    last_error_code = models.CharField(max_length=32, blank=True)
    # Снимок инструментов MCP-сервера: имя, название, описание, схема параметров
    # и отметка «только чтение». Обновляется только по кнопке (SPEC-0023 R-2).
    tools = models.JSONField(default=list, blank=True)
    tools_refreshed_at = models.DateTimeField(null=True, blank=True)
    # Версия runtime-настроек LLM. Event-workers держат circuit breaker в своей
    # памяти и заменяют его после исправления конфигурации провайдера.
    runtime_revision = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["provider", "name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "provider", "name"], name="uniq_integration_org_provider_name"),
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.name}"
