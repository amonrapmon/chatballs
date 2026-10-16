"""Правило обработки обращений и журнал его исполнений.

Правило — настройка организации: одна строка на каждое назначение из каталога.
Запись журнала — одно логическое действие по одному исходному событию. Её
уникальность и есть защита от повтора: сколько бы раз ни пришло событие и ни
перезапустился воркер, второй строки с тем же ключом не появится.
"""

from django.conf import settings
from django.db import models

from chatballs.tenancy.models import TenantRelationModel

# Сутки, как и у порогов очереди: всё, что дольше, — уже другая задача.
MAX_DELAY_MINUTES = 24 * 60
# Текст подтверждения — одно сообщение клиенту, а не письмо.
MAX_TEXT_LENGTH = 1000


class HandlingRuleKind(models.TextChoices):
    RECEIPT_CONFIRMATION = "RECEIPT_CONFIRMATION"
    WAIT_EXCEEDED_NOTICE = "WAIT_EXCEEDED_NOTICE"
    REPLY_REMINDER = "REPLY_REMINDER"
    ASSIGNMENT_RETURN = "ASSIGNMENT_RETURN"


class RuleAction(models.TextChoices):
    RETURN_TO_QUEUE = "RETURN_TO_QUEUE"
    SEND_CONFIRMATION = "SEND_CONFIRMATION"
    NOTIFY_WAIT_EXCEEDED = "NOTIFY_WAIT_EXCEEDED"
    REMIND_REPLY = "REMIND_REPLY"


# Действия, которые выполняются сразу по исходному факту. Срок правила у них —
# не отсрочка, а обещание: подтверждение называет его клиенту.
IMMEDIATE_ACTIONS = frozenset({RuleAction.SEND_CONFIRMATION})


class RuleExecutionStatus(models.TextChoices):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class RuleExecutionReason(models.TextChoices):
    """Почему действие не выполнено. Код, а не фраза: журнал читают на разных языках."""

    RULE_DISABLED = "rule_disabled"
    CONVERSATION_NOT_OPEN = "conversation_not_open"
    ASSIGNMENT_REMOVED = "assignment_removed"
    ASSIGNMENT_REPLACED = "assignment_replaced"
    ASSIGNMENT_ACCEPTED = "assignment_accepted"
    NOT_WAITING = "not_waiting"
    REPLIED = "replied"
    CONDITION_NOT_MET = "condition_not_met"
    SETTINGS_INCOMPLETE = "settings_incomplete"
    CONNECTION_MISSING = "connection_missing"
    NO_RECIPIENTS = "no_recipients"
    EXECUTION_ERROR = "execution_error"


class RuleRecipient(models.TextChoices):
    """Кого оповещает правило. Код из каталога, получателей считает сервер."""

    CONVERSATION_GROUP = "CONVERSATION_GROUP"
    ASSIGNEE = "ASSIGNEE"
    GROUP_SUPERVISORS = "GROUP_SUPERVISORS"
    MANAGEMENT = "MANAGEMENT"


class HandlingRule(models.Model):
    organization = models.ForeignKey(
        "identity.Organization", on_delete=models.CASCADE, related_name="handling_rules"
    )
    kind = models.CharField(max_length=24, choices=HandlingRuleKind.choices)
    enabled = models.BooleanField(default=False)
    # Растёт на каждое изменение настройки. Запись журнала помнит версию, по
    # которой она запланирована и выполнена.
    version = models.PositiveIntegerField(default=1)
    delay_minutes = models.PositiveIntegerField(null=True, blank=True)
    # Только ключи и коды из каталога (rules.catalog): ни выражений, ни кода.
    conditions = models.JSONField(default=dict, blank=True)
    recipients = models.JSONField(default=list, blank=True)
    # Текст сообщения клиенту. Своего текста у сервера нет: пусто — значит
    # отправлять нечего.
    text = models.TextField(blank=True, default="")
    updated_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "kind"], name="uniq_handling_rule_org_kind"
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=HandlingRuleKind.values),
                name="handling_rule_kind_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(version__gt=0), name="handling_rule_version_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(delay_minutes__isnull=True)
                | models.Q(delay_minutes__gte=1, delay_minutes__lte=MAX_DELAY_MINUTES),
                name="handling_rule_delay_range",
            ),
            # Включённое правило без срока выполнять не по чему.
            models.CheckConstraint(
                condition=models.Q(enabled=False) | models.Q(delay_minutes__isnull=False),
                name="handling_rule_enabled_has_delay",
            ),
        ]

    def __str__(self) -> str:
        return f"handling-rule:{self.organization_id}/{self.kind}"


class RuleExecution(TenantRelationModel):
    tenant_relation_fields = ("rule", "conversation", "source_event")
    rule = models.ForeignKey(HandlingRule, on_delete=models.CASCADE, related_name="executions")
    rule_version = models.PositiveIntegerField()
    conversation = models.ForeignKey(
        "conversations.Conversation", on_delete=models.CASCADE, related_name="rule_executions"
    )
    # Факт, от которого идёт срок: конкретное назначение, вход в очередь.
    source_event = models.ForeignKey(
        "conversations.ConversationEvent", on_delete=models.CASCADE, related_name="rule_executions"
    )
    action = models.CharField(max_length=24, choices=RuleAction.choices)
    # С какого момента идёт срок, если не с самого факта: ожидание ответа
    # начинает сообщение клиента, а факта у него нет.
    started_at = models.DateTimeField(null=True, blank=True)
    scheduled_for = models.DateTimeField()
    # Когда действие выполнено, пропущено или окончательно не удалось.
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=8, choices=RuleExecutionStatus.choices, default=RuleExecutionStatus.PENDING
    )
    # Код причины пропуска или ошибки (RuleExecutionReason). Текста исключения,
    # содержимого переписки и внутренних сведений здесь нет.
    reason = models.CharField(max_length=32, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    # Что получилось: сообщение в ленте и оклик, по которому видно получателя.
    message = models.ForeignKey(
        "conversations.Message", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    notification = models.ForeignKey(
        "notifications.Notification", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Кого оповестили лично. Снимок идентификаторов, как в доменных фактах:
    # увольнение сотрудника не должно переписывать журнал.
    recipient_user_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scheduled_for", "-id"]
        indexes = [
            models.Index(
                fields=["organization", "scheduled_for"], name="rule_execution_period_idx"
            ),
            models.Index(fields=["conversation", "status"], name="rule_execution_pending_idx"),
        ]
        constraints = [
            # Логический ключ действия: организация, правило, исходное событие
            # и вид действия.
            models.UniqueConstraint(
                fields=["organization", "rule", "source_event", "action"],
                name="uniq_rule_execution_logical_key",
            ),
            models.CheckConstraint(
                condition=models.Q(action__in=RuleAction.values), name="rule_execution_action_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=RuleExecutionStatus.values),
                name="rule_execution_status_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status=RuleExecutionStatus.PENDING, finished_at__isnull=True)
                | (
                    ~models.Q(status=RuleExecutionStatus.PENDING)
                    & models.Q(finished_at__isnull=False)
                ),
                name="rule_execution_finished_matches_status",
            ),
            # Пропуск и ошибка всегда объяснены, исполнение и ожидание — нет.
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=[RuleExecutionStatus.SKIPPED, RuleExecutionStatus.FAILED]
                    )
                    & ~models.Q(reason="")
                )
                | models.Q(
                    status__in=[RuleExecutionStatus.PENDING, RuleExecutionStatus.EXECUTED],
                    reason="",
                ),
                name="rule_execution_reason_matches_status",
            ),
        ]

    def __str__(self) -> str:
        return f"rule-execution:{self.conversation_id}/{self.action}/{self.status}"
