"""HTTP API правил обработки обращений и журнала их исполнений.

Настройки читает тот, кто видит настройки организации, меняет — тот, кто ими
управляет (OWNER, ADMIN). Всё, что прислал клиент, проверяется каталогом на
сервере: неизвестное поле, условие или получатель — ошибка, а не молчаливый
пропуск.
"""

from __future__ import annotations

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.pagination import page_payload, paginate
from chatballs.api.permissions import HasCapability
from chatballs.conversations.rules.catalog import CATALOG, EDITABLE_FIELDS
from chatballs.conversations.rules.deadline_text import placeholder
from chatballs.conversations.rules.journal import (
    execution_payload,
    journal_for,
    recipient_names,
)
from chatballs.conversations.rules.models import (
    MAX_DELAY_MINUTES,
    MAX_TEXT_LENGTH,
    HandlingRule,
)
from chatballs.conversations.rules.settings import rules_for, update_rule
from chatballs.i18n import t

_API_FIELDS = {api: field for field, api in EDITABLE_FIELDS.items()}


def rule_payload(rule: HandlingRule) -> dict[str, object]:
    spec = CATALOG[rule.kind]
    author = rule.updated_by
    return {
        "kind": rule.kind,
        "version": rule.version,
        **{api: getattr(rule, field) for field, api in EDITABLE_FIELDS.items()},
        "updatedAt": rule.updated_at.isoformat() if rule.updated_at else None,
        "updatedBy": (author.full_name or author.email) if author else "",
        # Что у этого правила вообще настраивается: интерфейсу незачем знать
        # каталог наизусть и нельзя предлагать то, чего сервер не примет.
        "catalog": {
            "conditions": sorted(spec.conditions),
            "recipients": sorted(spec.recipients),
            "requiresText": spec.requires_text,
            "maxDelayMinutes": MAX_DELAY_MINUTES,
            "maxTextLength": MAX_TEXT_LENGTH,
            "deadlinePlaceholder": placeholder() if spec.requires_text else "",
        },
    }


def _changes(data: object) -> dict[str, object]:
    if not isinstance(data, dict) or not set(data) <= set(_API_FIELDS):
        raise ValidationError({"detail": t("rules.settings_invalid")})
    return {_API_FIELDS[name]: value for name, value in data.items()}


class RuleListView(APIView):
    permission_classes = [HasCapability]
    required_capability = "settings.view"

    def get(self, request: Request) -> Response:
        rules = rules_for(request.tenant_context.organization_id)
        return Response({"items": [rule_payload(rule) for rule in rules]})


class RuleDetailView(APIView):
    permission_classes = [HasCapability]
    required_capability = "settings.manage"

    def patch(self, request: Request, kind: str) -> Response:
        if kind not in CATALOG:
            raise NotFound(t("rules.not_found"))
        rule = update_rule(
            context=request.tenant_context, kind=kind, changes=_changes(request.data)
        )
        return Response({"rule": rule_payload(rule)})


class RuleExecutionListView(APIView):
    """Журнал отдаётся страницами; область доступа считает rules.journal."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        context = request.tenant_context
        page = paginate(journal_for(context, request.query_params), request.query_params)
        names = recipient_names(context.organization_id, page.items)
        return Response({
            **page_payload(page, lambda execution: execution_payload(execution, names)),
            "timezone": context.organization.timezone,
        })
