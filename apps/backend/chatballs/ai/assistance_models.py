"""Хранение помощи оператору (SPEC-0024 R-4, R-5, R-7).

Попытка объединяет исходное предложение и альтернативы; её состояние относится
к исходной генерации. Каждый вариант имеет
свою идемпотентную операцию и версию истории (непрозрачный revision/fingerprint).
Здесь нет отправки сообщений, вызова AI или изменения управления диалогом.
Текст записывается после обратной подстановки; карта псевдонимов не хранится.
"""

import uuid

from django.db import models

from chatballs.ai.assistance_send_models import (
    ReplySuggestionSend as ReplySuggestionSend,
)
from chatballs.tenancy.models import TenantRelationModel


class ReplyAssistanceStatus(models.TextChoices):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    READY = "READY"
    ERROR = "ERROR"


class ReplyAssistanceError(models.TextChoices):
    GENERATION_FAILED = "GENERATION_FAILED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    PERMISSION_DENIED = "PERMISSION_DENIED"


class AssistanceOperation(TenantRelationModel):
    """Общие метаданные операции; только безопасный код ошибки, без ответа API."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    operation_key = models.CharField(max_length=160)
    requested_by = models.ForeignKey(
        "identity.OrganizationMembership", on_delete=models.PROTECT, related_name="+"
    )
    history_version = models.CharField(max_length=128)
    status = models.CharField(
        max_length=16, choices=ReplyAssistanceStatus.choices,
        default=ReplyAssistanceStatus.PENDING,
    )
    error_code = models.CharField(
        max_length=32, choices=ReplyAssistanceError.choices, blank=True, default=""
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "operation_key"], name="%(class)s_operation_uniq"
            ),
            models.CheckConstraint(
                condition=~models.Q(operation_key="") & ~models.Q(history_version=""),
                name="%(class)s_context_present",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status=ReplyAssistanceStatus.PENDING,
                             started_at__isnull=True, completed_at__isnull=True, error_code="")
                    | models.Q(status=ReplyAssistanceStatus.RUNNING,
                               started_at__isnull=False, completed_at__isnull=True, error_code="")
                    | models.Q(status=ReplyAssistanceStatus.READY,
                               started_at__isnull=False, completed_at__isnull=False, error_code="")
                    | models.Q(status=ReplyAssistanceStatus.ERROR, completed_at__isnull=False,
                               error_code__in=ReplyAssistanceError.values)
                ),
                name="%(class)s_state_valid",
            ),
            models.CheckConstraint(
                condition=(models.Q(started_at__isnull=True)
                           | models.Q(started_at__gte=models.F("created_at")))
                & (models.Q(completed_at__isnull=True)
                   | models.Q(completed_at__gte=models.F("created_at")))
                & (models.Q(started_at__isnull=True) | models.Q(completed_at__isnull=True)
                   | models.Q(completed_at__gte=models.F("started_at"))),
                name="%(class)s_time_valid",
            ),
        ]


class ReplyAssistanceAttempt(AssistanceOperation):
    tenant_relation_fields = ("conversation", "agent", "requested_by")

    conversation = models.ForeignKey(
        "conversations.Conversation", on_delete=models.PROTECT,
        related_name="reply_assistance_attempts",
    )
    agent = models.ForeignKey(
        "ai.AIAgent", on_delete=models.PROTECT, related_name="reply_assistance_attempts"
    )

    class Meta(AssistanceOperation.Meta):
        abstract = False
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self) -> str:
        return f"reply-assistance:{self.public_id}/{self.status}"


class ReplySuggestion(AssistanceOperation):
    tenant_relation_fields = ("attempt", "requested_by", "rejected_by")

    attempt = models.ForeignKey(
        ReplyAssistanceAttempt, on_delete=models.PROTECT, related_name="suggestions"
    )
    position = models.PositiveIntegerField()
    # Не редактируемый черновик: исходный результат AI после обратной подстановки.
    original_text = models.TextField(blank=True, default="")
    rejected_by = models.ForeignKey(
        "identity.OrganizationMembership", on_delete=models.PROTECT,
        related_name="+", null=True, blank=True,
    )
    rejected_at = models.DateTimeField(null=True, blank=True)

    class Meta(AssistanceOperation.Meta):
        abstract = False
        ordering = ["position", "id"]
        constraints = [
            *AssistanceOperation.Meta.constraints,
            models.UniqueConstraint(
                fields=["attempt", "position"], name="reply_suggestion_position_uniq"
            ),
            models.CheckConstraint(
                condition=models.Q(position__gte=1), name="reply_suggestion_position_valid"
            ),
            models.CheckConstraint(
                condition=(models.Q(status=ReplyAssistanceStatus.READY)
                           & ~models.Q(original_text=""))
                | (~models.Q(status=ReplyAssistanceStatus.READY) & models.Q(original_text="")),
                name="reply_suggestion_text_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(rejected_by__isnull=True, rejected_at__isnull=True)
                | models.Q(status=ReplyAssistanceStatus.READY, rejected_by__isnull=False,
                           rejected_at__isnull=False,
                           rejected_at__gte=models.F("completed_at")),
                name="reply_suggestion_rejection_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"reply-suggestion:{self.public_id}/{self.status}"
