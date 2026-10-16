"""Contact and connection identity data; public imports remain in models.py."""

from django.conf import settings
from django.db import models

from chatballs.conversations.upload_paths import contact_avatar_upload_path
from chatballs.tenancy.models import TenantRelationModel


class Contact(models.Model):
    organization = models.ForeignKey("identity.Organization", on_delete=models.PROTECT, related_name="contacts")
    name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True, default="")
    # Телефон приходит только через явный шаринг контакта (кнопка в TG/MAX,
    # форма в веб-чате) — автоматически мессенджеры его не отдают.
    phone = models.CharField(max_length=32, blank=True)
    # Внешний URL аватара контакта, если провайдер его отдаёт (например, MAX
    # присылает avatar_url в профиле отправителя). Telegram не отдаёт фото в
    # getUpdates, поэтому для него поле остаётся пустым. Хранится только URL —
    # само изображение живёт на стороне провайдера.
    avatar_url = models.URLField(max_length=512, blank=True, default="")
    # Фото контакта, скачанное у провайдера и лежащее у нас. Внешней ссылкой
    # обойтись нельзя: страница рабочего места живёт под CSP `img-src 'self'`,
    # и картинка с чужого домена до экрана не доезжает — оператор видит
    # инициалы вместо фото. Источник запоминается, чтобы не качать то же самое
    # на каждое сообщение.
    avatar = models.FileField(
        upload_to=contact_avatar_upload_path, max_length=512, blank=True, default=""
    )
    avatar_content_type = models.CharField(max_length=64, blank=True, default="")
    avatar_source = models.CharField(max_length=512, blank=True, default="")
    # Карточка контакта (дизайн-базлайн v2, решение 5): описание, компания, город —
    # заполняет оператор.
    description = models.TextField(blank=True, default="")
    company = models.CharField(max_length=160, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    # Контакт, в который этот был объединён (ADR-CHATBALLS-0006). Строка не удаляется:
    # объединение обратимо, поэтому исходный контакт остаётся для разъединения.
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="merged_contacts",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Триграммные индексы для поиска подстрокой (имя, телефон) заведены в
    # миграции 0020 сырым SQL: Django 5.2 рендерит функциональный индекс с
    # opclass без внутренних скобок — «(UPPER(name) gin_trgm_ops)», и Postgres
    # такой синтаксис не принимает.

    def __str__(self) -> str:
        return self.name or f"contact:{self.id}"


class ContactFieldValue(TenantRelationModel):
    """Последнее значение с сайта для контакта и WEB-подключения."""

    tenant_relation_fields = ("contact", "integration")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="site_field_values")
    integration = models.ForeignKey(
        "integrations.Integration", on_delete=models.CASCADE, related_name="contact_field_values"
    )
    key = models.CharField(max_length=40)
    value = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "contact_field_values"
        constraints = [
            models.UniqueConstraint(
                fields=["contact", "integration", "key"], name="uniq_contact_integration_field_key"
            ),
        ]


class ContactMerge(models.Model):
    """Журнал объединения контактов (ADR-CHATBALLS-0006).

    Хранит, что именно переехало, чтобы объединение можно было развернуть
    обратно: перенесённые идентичности и диалоги и поля карточки, которые были
    заполнены из исходного контакта.
    """

    organization = models.ForeignKey("identity.Organization", on_delete=models.PROTECT, related_name="contact_merges")
    target = models.ForeignKey(Contact, on_delete=models.PROTECT, related_name="merges_in")
    source = models.ForeignKey(Contact, on_delete=models.PROTECT, related_name="merges_out")
    reason = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    moved_identity_ids = models.JSONField(default=list, blank=True)
    moved_conversation_ids = models.JSONField(default=list, blank=True)
    filled_fields = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reverted_at = models.DateTimeField(null=True, blank=True)
    reverted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    revert_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"merge:{self.source_id}->{self.target_id}"


class ConnectionIdentity(TenantRelationModel):
    tenant_relation_fields = ("contact", "connection")
    # Устойчивая идентичность контакта внутри конкретного подключения (ADR-CHATBALLS-0006).
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="identities")
    connection = models.ForeignKey("integrations.Integration", on_delete=models.PROTECT, related_name="identities")
    external_user_id = models.CharField(max_length=128)
    display_name = models.CharField(max_length=255, blank=True)
    # Публичный логин в мессенджере (@username в TG/MAX); пустой, если не задан.
    username = models.CharField(max_length=128, blank=True)
    # Когда подключение отдало подтверждённый телефон (кнопка «поделиться
    # контактом»). Только такая идентичность считается подтверждённой
    # (ADR-CHATBALLS-0006) — колонка «Статус» на вкладке «Идентификаторы».
    phone_verified_at = models.DateTimeField(null=True, blank=True, db_default=None)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["connection", "external_user_id"], name="uniq_identity_connection_user"),
        ]

    def __str__(self) -> str:
        return f"{self.connection_id}:{self.external_user_id}"
