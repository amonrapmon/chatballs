"""Server APIs require no new UI or operator grants."""

from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from chatballs.conversations.history_selectors import customer_visible_messages
from chatballs.conversations.models import Message
from chatballs.conversations.support_filters import parse_filters
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t
from chatballs.tenancy.database import tenant_atomic

from .access import require_quality_conversation
from .corrections import append_quality_correction
from .criteria import configure_quality, require_management
from .settings_presentation import criteria_value_literals, scale_catalog
from .models import QualitySettings
from .presentation import job_payload
from .queue import MissingCompletionHistory, launch_quality
from .selectors import job_for_context, quality_jobs, report_jobs


def body(request, allowed, required=()):
    data = request.data
    if not isinstance(data, dict) or set(data) - set(allowed) or set(required) - set(data):
        raise ValidationError(t("quality.request_invalid"))
    return data


class QualityViewBase(ConversationViewBase):
    def handle_exception(self, exc):
        response = super().handle_exception(exc)
        if isinstance(exc, MissingCompletionHistory):
            response.data.update(state="unavailable", errorCode="missing_history")
        return response

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response

    def payload(self, request, job):
        return job_payload(job, request.tenant_context)


class QualitySettingsView(QualityViewBase):
    required_capability = "settings.manage"

    def get(self, request):
        require_management(request.tenant_context)
        settings = QualitySettings.objects.filter(organization_id=request.tenant_context.organization_id).first()
        version = settings.current_version if settings else None
        return Response({"enabled": settings.enabled if settings else False,
                         "criteriaVersion": version.version if version else None,
                         "nextCriteriaVersion": version.version + 1 if version else 1,
                         "criteriaCreatedAt": version.created_at.isoformat() if version else None,
                         "criteria": version.criteria if version else [], "scales": scale_catalog(),
                         "criteriaValueLiterals": criteria_value_literals(version.criteria) if version else {}})

    def put(self, request):
        data = body(request, ("enabled", "criteria"), ("enabled",))
        configure_quality(context=request.tenant_context, enabled=data["enabled"], criteria=data.get("criteria"))
        return self.get(request)


class QualityLaunchView(QualityViewBase):
    required_capability = "settings.manage"

    def post(self, request, conversation_id):
        data = body(request, ("operationId", "repeat"), ("operationId",))
        with tenant_atomic(request.tenant_context):
            job = launch_quality(context=request.tenant_context, conversation_id=conversation_id,
                                 operation_id=data["operationId"], repeat=data.get("repeat", False))
            return Response(self.payload(request, job), status=202)


class QualityConversationView(QualityViewBase):
    def get(self, request, conversation_id):
        require_quality_conversation(request.tenant_context, conversation_id)
        return Response({"jobs": [self.payload(request, job) for job in quality_jobs(
            request.tenant_context).filter(conversation_id=conversation_id)]})


class QualityJobView(QualityViewBase):
    def get(self, request, job_id):
        return Response(self.payload(request, job_for_context(request.tenant_context, job_id)))


class QualityReportView(QualityViewBase):
    def get(self, request):
        filters = parse_filters(request.query_params)
        jobs = report_jobs(request.tenant_context, filters)
        # Explicitly versioned rows; no averaging unrelated scales.
        return Response({"period": filters.payload(), "jobs": [self.payload(request, job) for job in jobs]})


class QualityCorrectionView(QualityViewBase):
    def post(self, request, job_id):
        data = body(request, ("expectedRevision", "criterionCode", "value", "scaleIndex", "reason"),
                    ("expectedRevision", "criterionCode", "reason"))
        if ("value" in data) == ("scaleIndex" in data):
            raise ValidationError(t("quality.request_invalid"))
        job = job_for_context(request.tenant_context, job_id)
        result = getattr(job, "result", None)
        if result is None:
            raise ValidationError(t("quality.result_invalid"))
        append_quality_correction(context=request.tenant_context, result_id=result.pk,
                                  expected_revision=data["expectedRevision"], criterion_code=data["criterionCode"],
                                  value=data.get("value"), scale_index=data.get("scaleIndex"), reason=data["reason"])
        return Response(self.payload(request, job))


class QualityEvidenceView(QualityViewBase):
    def get(self, request, job_id, message_id):
        job = job_for_context(request.tenant_context, job_id)
        result = getattr(job, "result", None)
        evidence = {pk for row in result.data.get("conclusions", []) for pk in row["messageIds"]} if result else set()
        message = customer_visible_messages(Message.objects.filter(
            pk=message_id, organization_id=request.tenant_context.organization_id,
            conversation_id=job.conversation_id, system_event="", author_type__in=("CONTACT", "OPERATOR", "AI"),
        )).first() if message_id in evidence else None
        if message is None:
            raise NotFound(t("quality.not_found"))
        return Response({"messageId": message.pk, "conversationId": message.conversation_id,
                         "authorType": message.author_type, "createdAt": message.created_at.isoformat(),
                         "text": message.text, "contentHtml": message.content_html, "transcript": message.transcript})
