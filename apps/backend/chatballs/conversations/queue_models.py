"""Пороги очереди: через сколько напоминать, расширять круг и звать руководство.

Числа разные у разных организаций — у круглосуточной поддержки хостинга и у
клиники с приёмом по будням «долго» означает не одно и то же, — поэтому они
настройка, а не константа в коде. Строка одна на организацию и заводится с
дефолтами при первом обращении.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class QueueEscalationPolicy(models.Model):
    organization = models.OneToOneField(
        "identity.Organization", on_delete=models.CASCADE, related_name="queue_policy"
    )
    # Диалог ждёт дольше этого — повторный оклик той же группе.
    remind_after_minutes = models.PositiveIntegerField(default=5)
    # Ждёт ещё дольше — круг расширяется за пределы группы диалога.
    widen_after_minutes = models.PositiveIntegerField(default=15)
    # Совсем долго — это уже не про сменщика, а про руководство.
    escalate_after_minutes = models.PositiveIntegerField(default=30)
    # Назначили ответственного, а он не взял — диалог возвращается в общую
    # очередь. Без этого назначение работает как способ спрятать диалог: из
    # общей очереди он ушёл, а отвечать некому.
    assignment_timeout_minutes = models.PositiveIntegerField(default=10)
    # Кто и когда менял: в разделе настроек это подпись под формой. Сроки —
    # правило работы смены, и знать, чьё это решение, важнее, чем кажется.
    updated_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    # Значения по умолчанию — они же «обычные сроки» в кнопке сброса.
    DEFAULTS = {
        "remind_after_minutes": 5,
        "widen_after_minutes": 15,
        "escalate_after_minutes": 30,
        "assignment_timeout_minutes": 10,
    }

    class Meta:
        db_table = "conversations_queueescalationpolicy"

    def __str__(self) -> str:
        return f"queue-policy:{self.organization_id}"


def policy_for(organization) -> QueueEscalationPolicy:
    policy, _ = QueueEscalationPolicy.objects.get_or_create(organization=organization)
    return policy
