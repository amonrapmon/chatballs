"""Summaries never combine criterion versions or interpret string labels."""

from chatballs.conversations.quality.models import QualityCriteriaVersion, QualityJob
from chatballs.identity.models import EmployeeRole


def version_catalog(context, conversations, now):
    versions = list(QualityCriteriaVersion.objects.filter(
        organization_id=context.organization_id, created_at__lte=now,
    ).order_by("version"))
    allowed = None
    if context.membership.role == EmployeeRole.SUPERVISOR:
        allowed = set(QualityJob.objects.filter(
            organization_id=context.organization_id,
            conversation_id__in=conversations.values("pk"),
        ).values_list("criteria_version_id", flat=True))
    return [{"criteriaVersionId": version.pk, "criteriaVersion": version.version,
             "validFrom": version.created_at.isoformat(),
             "validTo": versions[index + 1].created_at.isoformat() if index + 1 < len(versions) else None,
             "criteria": version.criteria}
            for index, version in enumerate(versions) if allowed is None or version.pk in allowed]


def score_summary(criterion, values):
    known = [value for value in values if value is not None]
    positive = criterion.get("reporting", {}).get("positiveValue")
    if "positiveValue" in criterion.get("reporting", {}):
        return {"kind": "positiveRate", "positiveValue": positive,
                "value": sum(type(value) is type(positive) and value == positive for value in known)
                / len(known) if known else None}
    if all(type(value) in (int, float) for value in criterion["scale"]):
        return {"kind": "mean", "value": sum(known) / len(known) if known else None}
    return {"kind": "unavailable", "value": None}


def quality_versions(catalog, rows):
    versions = []
    for metadata in reversed(catalog):
        jobs = [row for row in rows if row["criteriaVersionId"] == metadata["criteriaVersionId"]]
        succeeded = [row for row in jobs if row["state"] == "SUCCEEDED"]
        count = len(succeeded)
        corrected = sum(row["correctionRevision"] > 0 for row in succeeded)
        criteria = []
        for criterion in metadata["criteria"]:
            conclusions = [item for row in succeeded for item in row["conclusions"]
                           if item["code"] == criterion["code"]]
            original = [item["originalValue"] for item in conclusions]
            effective = [item["effectiveValue"] for item in conclusions]
            criteria.append({"code": criterion["code"], "name": criterion.get("name", criterion["description"]),
                             "description": criterion["description"], "scale": criterion["scale"],
                             "scoredCount": sum(value is not None for value in effective) if count else None,
                             "missingCount": sum(value is None for value in effective) if count else None,
                             "correctedCount": sum(item["corrected"] for item in conclusions) if count else None,
                             "originalSummary": score_summary(criterion, original),
                             "effectiveSummary": score_summary(criterion, effective)})
        versions.append({**{key: value for key, value in metadata.items() if key != "criteria"},
                         "analysisCount": count, "selectedJobCount": len(jobs),
                         "correctedAnalysisCount": corrected, "correctionRate": corrected / count if count else None,
                         "criteria": criteria})
    return versions
