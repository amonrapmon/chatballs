"""Сроки очереди: раздел «Когда звать на помощь» (макет Q2).

До этого пороги правились только в служебной админке — то есть де-факто никем.
Читает их тот, кто видит настройки; меняет — тот, кто ими управляет.
"""

from __future__ import annotations

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.conversations.queue_models import QueueEscalationPolicy, policy_for
from chatballs.i18n import t
from chatballs.identity.policy import ResourceScope, authorize

FIELDS = tuple(QueueEscalationPolicy.DEFAULTS)
# Сутки: всё, что дольше, — это не «позвать на помощь», а другая задача.
MAX_MINUTES = 24 * 60


def _payload(policy: QueueEscalationPolicy) -> dict:
    author = policy.updated_by
    return {
        **{field: getattr(policy, field) for field in FIELDS},
        "defaults": dict(QueueEscalationPolicy.DEFAULTS),
        "updatedAt": policy.updated_at.isoformat() if policy.updated_at else None,
        "updatedBy": (author.full_name or author.email) if author else "",
    }


class QueuePolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        context = request.tenant_context
        if not authorize(context.membership, "settings.view", ResourceScope(context.organization_id)):
            return Response({"detail": t("settings.queue_policy_forbidden")}, status=403)
        return Response(_payload(policy_for(context.organization)))

    def patch(self, request: Request) -> Response:
        context = request.tenant_context
        if not authorize(context.membership, "settings.manage", ResourceScope(context.organization_id)):
            return Response({"detail": t("settings.queue_policy_forbidden")}, status=403)
        policy = policy_for(context.organization)
        changed = []
        for field in FIELDS:
            if field not in request.data:
                continue
            value = request.data[field]
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_MINUTES:
                return Response({"detail": t("settings.queue_minutes_range")}, status=400)
            if getattr(policy, field) != value:
                setattr(policy, field, value)
                changed.append(field)
        if changed:
            policy.updated_at = timezone.now()
            policy.updated_by = context.actor_user
            policy.save(update_fields=[*changed, "updated_at", "updated_by"])
        return Response(_payload(policy))
