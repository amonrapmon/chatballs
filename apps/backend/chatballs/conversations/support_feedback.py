"""Persisted feedback in the current report scope; no AI calls or normalization."""

from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.quality.models import QualityJob
from chatballs.conversations.support_quality_summary import quality_versions, version_catalog
from chatballs.conversations.support_rating_summary import rating_summaries
from chatballs.identity.models import EmployeeRole
from chatballs.ratings.models import CustomerRating, RatingRequest
from chatballs.ratings.results import protected_payload, scale_groups


def _dimensions(event):
    return {"group": event.group_id, "connection": event.connection_id, "transport": event.transport}


def _matches(filters, event, responders):
    return (filters.employee is None or filters.employee in responders) and filters.matches(
        event, employee=filters.employee,
    )


def _quality_groups(rows):
    groups = {}
    for row in rows:
        for conclusion in row["conclusions"]:
            key = (row["criteriaVersionId"], conclusion["code"])
            group = groups.setdefault(key, {
                "criteriaVersionId": row["criteriaVersionId"], "criteriaVersion": row["criteriaVersion"],
                "code": conclusion["code"], "scale": conclusion["scale"], "count": 0,
                "originalValues": [{"value": value, "count": 0} for value in conclusion["scale"]],
                "effectiveValues": [{"value": value, "count": 0} for value in conclusion["scale"]],
            })
            group["count"] += 1
            for source, target in (("originalValue", "originalValues"), ("effectiveValue", "effectiveValues")):
                for bucket in group[target]:
                    if type(bucket["value"]) is type(conclusion[source]) and bucket["value"] == conclusion[source]:
                        bucket["count"] += 1
    return list(groups.values())


def _quality_summary(rows, catalog, permitted=True):
    return {"state": "available" if permitted else "forbidden", "periodBasis": "completed_at",
            "revisionPolicy": "latest_per_completion", "count": len(rows) if permitted else None,
            "states": {state: sum(row["state"] == state for row in rows)
                       for state in ("WAITING", "RUNNING", "SUCCEEDED", "FAILED")} if permitted else {},
            "groups": _quality_groups(rows), "details": rows,
            "versions": quality_versions(catalog, rows) if permitted else []}


def _rating_summary(results, rows, requests, cutoff, permitted=True):
    return {"state": "available" if permitted else "forbidden", "periodBasis": "received_at",
            "count": len(results) if permitted else None, "groups": scale_groups(results), "details": rows,
            "scaleSummaries": rating_summaries(rows, requests, cutoff) if permitted else []}


def _quality_rows(context, conversations, filters, now, staff_ids):
    completions = {event.operation_id: event for event in ConversationEvent.objects.filter(
        organization_id=context.organization_id, conversation_id__in=conversations.values("pk"),
        event_type="CLOSED", occurred_at__gte=filters.start, occurred_at__lt=filters.end,
        occurred_at__lte=now,
    )}
    jobs = QualityJob.objects.filter(
        organization_id=context.organization_id, conversation_id__in=conversations.values("pk"),
        completion_event_id__in=completions,
    ).select_related("criteria_version", "result").prefetch_related("result__corrections").order_by(
        "conversation_id", "completion_event_id", "-revision", "-pk",
    )
    seen, rows = set(), []
    for job in jobs:
        key = (job.conversation_id, job.completion_event_id)
        if key in seen:
            continue
        seen.add(key)
        event = completions[job.completion_event_id]
        responders = sorted({message["author_user_id"] for message in job.history_snapshot
                             if message["author_type"] == "OPERATOR" and message["author_user_id"] is not None})
        if not _matches(filters, event, responders):
            continue
        result = getattr(job, "result", None)
        corrections = list(result.corrections.all()) if result else []
        effective = {item.criterion_code: item.value for item in corrections}
        criteria = {item["code"]: item for item in job.criteria_version.criteria}
        conclusions = [{"code": item["code"], "scale": criteria[item["code"]]["scale"],
                        "originalValue": item["value"], "effectiveValue": effective.get(item["code"], item["value"]),
                        "corrected": item["code"] in effective,
                        "missingReason": item.get("missingReason")}
                       for item in result.data.get("conclusions", [])] if result else []
        rows.append({"id": job.pk, "conversationId": job.conversation_id,
                     "completionEventId": str(job.completion_event_id), "completedAt": job.completed_at.isoformat(),
                     "revision": job.revision, "historyRevision": job.history_revision,
                     "criteriaVersionId": job.criteria_version_id, "criteriaVersion": job.criteria_version.version,
                     "responderIds": [pk for pk in responders if pk in staff_ids],
                     "state": job.state, "errorCode": job.error_code or None,
                     "correctionRevision": corrections[-1].revision if corrections else 0,
                     "conclusions": conclusions, **_dimensions(event)})
    return rows


def report_feedback(*, context, conversations, members, filters, now):
    """Caller supplies the freshly authorized scope inside tenant_atomic."""
    permitted = context.membership.role != EmployeeRole.EMPLOYEE
    staff_ids = {member.user_id for member in members}
    ratings, rating_rows, quality_rows, requests, catalog = [], [], [], [], []
    cutoff = min(filters.end, now)
    if permitted:
        source = CustomerRating.objects.filter(
            organization_id=context.organization_id, request__conversation_id__in=conversations.values("pk"),
            received_at__gte=filters.start, received_at__lt=filters.end, received_at__lte=now,
        ).select_related("request__completion").order_by("received_at", "pk")
        for result in source:
            event = result.request.completion
            if _matches(filters, event, result.request.responder_ids):
                ratings.append(result)
                rating_rows.append({**protected_payload(result, permitted_staff_ids=staff_ids), **_dimensions(event)})
        quality_rows = _quality_rows(context, conversations, filters, now, staff_ids)
        source = RatingRequest.objects.filter(
            organization_id=context.organization_id, conversation_id__in=conversations.values("pk"),
            sent_at__gte=filters.start, sent_at__lt=filters.end, sent_at__lte=now,
        ).select_related("completion", "result").order_by("sent_at", "pk")
        requests = [request for request in source if _matches(filters, request.completion, request.responder_ids)]
        catalog = version_catalog(context, conversations, now)
    employees = {}
    for member in members:
        own_ratings = [result for result in ratings if member.user_id in result.request.responder_ids]
        own_rating_rows = [row for row in rating_rows if member.user_id in row["responderIds"]]
        own_quality = [row for row in quality_rows if member.user_id in row["responderIds"]]
        own_requests = [request for request in requests if member.user_id in request.responder_ids]
        employees[member.user_id] = {
            "customerRatings": _rating_summary(own_ratings, own_rating_rows, own_requests, cutoff, permitted),
            "qualityAnalysis": _quality_summary(own_quality, catalog, permitted),
        }
    return {"customerRatings": _rating_summary(ratings, rating_rows, requests, cutoff, permitted),
            "qualityAnalysis": _quality_summary(quality_rows, catalog, permitted)}, employees
