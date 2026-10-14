"""Separate original values, effective decisions and append-only review history."""

from chatballs.conversations.history_selectors import customer_visible_messages
from chatballs.conversations.management_scope import management_scope
from chatballs.conversations.models import Message

from .access import require_quality_conversation
from .timing import temporal_facts


def job_payload(job, context):
    require_quality_conversation(context, job.conversation_id)
    scope = management_scope(context, forbidden_key="quality.forbidden")
    staff_ids = scope.staff_ids() | {scope.actor.user_id}
    organization_public_id = context.organization.public_id
    result = getattr(job, "result", None)
    corrections = list(result.corrections.select_related("author__user").all()) if result else []
    effective = {row.criterion_code: row.value for row in corrections}
    allowed = set(customer_visible_messages(Message.objects.filter(
        organization_id=job.organization_id, conversation_id=job.conversation_id,
        system_event="", author_type__in=("CONTACT", "OPERATOR", "AI"),
        pk__in=[item["id"] for item in job.history_snapshot],
    )).values_list("pk", flat=True))
    conclusions = []
    for row in result.data.get("conclusions", []) if result else []:
        evidence = [{"messageId": pk, "url": (
            f"/api/v1/organizations/{organization_public_id}/conversations/quality/jobs/{job.pk}/messages/{pk}/"
        )} for pk in row["messageIds"] if pk in allowed]
        conclusions.append({"code": row["code"], "originalValue": row["value"],
                            "effectiveValue": effective.get(row["code"], row["value"]),
                            "explanation": row["explanation"], "recommendations": row["recommendations"],
                            "evidence": evidence, "evidenceAvailable": len(evidence) == len(row["messageIds"])})
    return {"id": job.pk, "conversationId": job.conversation_id,
            "completionEventId": str(job.completion_event_id), "completedAt": job.completed_at.isoformat(),
            "revision": job.revision, "historyRevision": job.history_revision,
            "criteriaVersion": job.criteria_version.version, "criteria": job.criteria_version.criteria,
            "state": job.state, "errorCode": job.error_code or None,
            "startedAt": job.started_at.isoformat() if job.started_at else None,
            "finishedAt": job.finished_at.isoformat() if job.finished_at else None,
            "resultId": result.pk if result else None,
            "temporalFacts": result.data.get("temporalFacts") if result else temporal_facts(job),
            "conclusions": conclusions, "correctionRevision": corrections[-1].revision if corrections else 0,
            "corrections": [{"revision": row.revision, "criterionCode": row.criterion_code,
                             "value": row.value, "author": {"membershipId": row.author_id,
                             "userId": row.author.user_id, "name": row.author.user.full_name}
                             if row.author.user_id in staff_ids else None,
                             "createdAt": row.created_at.isoformat(), "reason": row.reason} for row in corrections]}
