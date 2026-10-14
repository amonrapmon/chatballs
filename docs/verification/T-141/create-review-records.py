"""Owner-authorized synthetic results; ONLY the disposable T-141 environment.

Execute through manage.py shell. No provider calls, new accounts or role changes.
Every result is explicitly a test record, not evidence of real AI performance.
"""

import hashlib
import json
import os
from uuid import uuid4

from django.db import transaction

from chatballs.ai.pseudonymization import Pseudonymizer
from chatballs.conversations.domain_events import record_fact, record_public_reply
from chatballs.conversations.lifecycle_services import close_conversation
from chatballs.conversations.models import ConnectionIdentity, Contact, Conversation, Message
from chatballs.conversations.quality.corrections import append_quality_correction
from chatballs.conversations.quality.criteria import configure_quality
from chatballs.conversations.quality.jobs import finish_quality_job, start_quality_job
from chatballs.conversations.quality.models import QualityJob, QualitySettings
from chatballs.conversations.quality.timing import temporal_facts
from chatballs.conversations.quality.validation import validate_output
from chatballs.identity.models import OrganizationMembership
from chatballs.ratings.models import RatingRequest, RatingSettings
from chatballs.ratings.public_service import submit_rating
from chatballs.ratings.settings_service import update_settings
from chatballs.ratings.web_delivery import deliver_due_requests
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.webchat.models import WebChatWidget, WebSession

assert os.environ.get("T141_REVIEW_PROJECT") == "skaro-chatballs-t-141", "Wrong environment"
MARKER = "T-141 · тестовая запись"
SCALE = [{"value": index + 1, "label": label} for index, label in enumerate(
    ["Очень плохо", "Плохо", "Нормально", "Хорошо", "Отлично"])]
CRITERIA = [
    {"code": "greeting", "name": "Приветствие", "description": "Сотрудник поздоровался и представился",
     "scale": ["Да", "Нет"], "reporting": {"positiveValue": "Да"}},
    {"code": "resolution", "name": "Решение вопроса", "description": "Решён или передан с понятным следующим шагом",
     "scale": [1, 2, 3, 4, 5]},
    {"code": "tone", "name": "Тон общения", "description": "Вежливо, без канцелярита и давления",
     "scale": [1, 2, 3, 4, 5]},
]


def review_conversation(widget, responders, values, rating_value, comment=""):
    connection = widget.integration
    contact = Contact.objects.create(organization=context.organization, name=f"{MARKER} {len(created) + 1}")
    identity = ConnectionIdentity.objects.create(
        organization=context.organization, connection=connection, contact=contact,
        external_user_id=f"t141-review-{uuid4()}",
    )
    WebSession.objects.create(
        organization=context.organization, connection=connection, widget=widget, identity=identity,
        token_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
    )
    conversation = Conversation.objects.create(
        organization=context.organization, channel=connection.channel, connection=connection,
        contact=contact, group=connection.channel.group, assigned_operator=responders[0].user,
        control_mode="HUMAN", transport_meta={"webChatWidgetId": widget.pk},
    )
    record_fact(conversation, "ACCEPTED", actor_kind="HUMAN", initiated_by_id=responders[0].user_id)
    for responder in responders:
        message = Message.objects.create(
            conversation=conversation, author_type="OPERATOR", author_user=responder.user,
            text=f"{MARKER}: здравствуйте, вопрос проверен, чек отправлен.",
        )
        record_public_reply(message)
    close_conversation(context=context, conversation_id=conversation.pk)
    job = QualityJob.objects.get(conversation=conversation)
    rows = [{"code": criterion["code"], "value": value, "explanation": f"{MARKER}: проверка отчёта.",
             "recommendations": [], "messageIds": [] if value is None else [message.pk],
             **({"missingReason": "insufficient_messages"} if value is None else {})}
            for criterion, value in zip(job.criteria_version.criteria, values, strict=True)]
    validated = validate_output(json.dumps({"conclusions": rows}), job, Pseudonymizer())
    validated["temporalFacts"] = temporal_facts(job)
    start_quality_job(context=context, job_id=job.pk)
    finish_quality_job(context=context, job_id=job.pk, validated_result=validated)
    deliver_due_requests(context)
    request = RatingRequest.objects.get(conversation=conversation)
    assert request.sent_at is not None, "Existing widget must support delivery"
    if rating_value is not None:
        submit_rating(request, context, {"value": rating_value, "comment": comment})
    created.append({"conversation": conversation.pk, "job": job.pk, "group": conversation.group_id,
                    "connection": connection.pk, "responders": [member.user_id for member in responders]})
    return job


with transaction.atomic(), tenant_atomic(1):
    assert not Contact.objects.filter(name__startswith=MARKER).exists(), "Review records already exist"
    assert not RatingSettings.objects.exists() and not QualitySettings.objects.exists(), "Settings changed: stop"
    admin = OrganizationMembership.objects.select_related("organization", "user").get(user_id=3, role="ADMIN")
    colleague = OrganizationMembership.objects.select_related("user").get(user_id=2, role="ADMIN")
    assert admin.blocked_at is None and colleague.blocked_at is None
    context = TenantContext.for_membership(admin)
    widgets = [WebChatWidget.objects.select_related("integration__channel__group").get(pk=pk) for pk in (1, 2)]
    assert all(widget.status == "PUBLISHED" and widget.integration.is_active for widget in widgets)
    created = []
    configure_quality(context=context, enabled=True, criteria=[{
        "code": "politeness", "name": "Вежливость", "description": "Вежливое общение", "scale": list(range(11)),
    }])
    configure_quality(context=context, enabled=True, criteria=CRITERIA)
    update_settings(context, {"enabled": True, "scale": SCALE, "text": "Как вам помогли?", "delaySeconds": 0})
    first = review_conversation(widgets[0], [admin, colleague], ["Да", 4, 5], 5, "Тестовая запись: спасибо.")
    append_quality_correction(context=context, result_id=first.result.pk, expected_revision=0,
                              criterion_code="resolution", value=5, reason=f"{MARKER}: проверка исправления.")
    review_conversation(widgets[1], [colleague], ["Нет", 2, 4], 4)
    criteria = [dict(criterion) for criterion in CRITERIA]
    criteria[-1]["scale"] = list(range(11))
    configure_quality(context=context, enabled=True, criteria=criteria)
    scale = [dict(choice) for choice in SCALE]
    scale[0]["label"] = "Не понравилось"
    update_settings(context, {"scale": scale})
    third = review_conversation(widgets[0], [admin], ["Да", None, 0], 2, "Тестовая запись: вопрос остался.")
    append_quality_correction(context=context, result_id=third.result.pk, expected_revision=0,
                              criterion_code="tone", value=6, reason=f"{MARKER}: проверка исходного нуля.")
    review_conversation(widgets[1], [admin], [None, 5, 10], None)
    update_settings(context, {"enabled": False})
    configure_quality(context=context, enabled=False)
    print(json.dumps({"testRecords": True, "conversations": created, "ratings": 3, "analyses": 4,
                      "newAccounts": 0, "newProviders": 0, "functionsEnabled": False}, ensure_ascii=False))
