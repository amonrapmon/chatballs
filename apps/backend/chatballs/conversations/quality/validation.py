"""Only complete, evidenced conclusions can become a successful analysis."""

import json

from chatballs.conversations.history_selectors import customer_visible_messages
from chatballs.conversations.models import Message


class InvalidQualityOutput(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidQualityOutput("duplicate_key")
        result[key] = value
    return result


def validate_output(text, job, pseudonymizer):
    try:
        output = json.loads(text, object_pairs_hook=_unique_object)
    except (ValueError, TypeError, RecursionError) as error:
        raise InvalidQualityOutput("invalid_json") from error
    if not isinstance(output, dict) or set(output) != {"conclusions"}:
        raise InvalidQualityOutput("invalid_shape")
    rows = output["conclusions"]
    criteria = {item["code"]: item for item in job.criteria_version.criteria}
    if not isinstance(rows, list) or len(rows) != len(criteria):
        raise InvalidQualityOutput("incomplete_criteria")
    snapshot_ids = {item["id"] for item in job.history_snapshot}
    allowed = set(customer_visible_messages(Message.objects.filter(
        organization_id=job.organization_id, conversation_id=job.conversation_id,
        pk__in=snapshot_ids, system_event="", author_type__in=("CONTACT", "OPERATOR", "AI"),
    )).values_list("pk", flat=True))
    conclusions, seen = [], set()
    for row in rows:
        required = {"code", "value", "explanation", "recommendations", "messageIds"}
        if (not isinstance(row, dict) or not required <= set(row)
                or set(row) - required - {"missingReason"}):
            raise InvalidQualityOutput("invalid_conclusion")
        code = row["code"]
        if isinstance(code, str):
            restored_code = pseudonymizer.restore(code)
            if restored_code.removed:
                raise InvalidQualityOutput("invalid_criterion")
            code = restored_code.text
        if not isinstance(code, str) or code not in criteria or code in seen:
            raise InvalidQualityOutput("invalid_criterion")
        value = row["value"]
        if isinstance(value, str):
            restored_value = pseudonymizer.restore(value)
            if restored_value.removed:
                raise InvalidQualityOutput("invalid_score")
            value = restored_value.text
        missing = value is None and row.get("missingReason") == "insufficient_messages"
        if ((value is None and not missing) or (value is not None and "missingReason" in row)
                or (not missing and not any(type(value) is type(v) and value == v for v in criteria[code]["scale"]))):
            raise InvalidQualityOutput("invalid_score")
        ids = row["messageIds"]
        if (not isinstance(ids, list) or (not ids and not missing) or any(type(v) is not int or v not in allowed for v in ids)
                or len(set(ids)) != len(ids)):
            raise InvalidQualityOutput("invalid_evidence")
        explanation, recommendations = row["explanation"], row["recommendations"]
        if (not isinstance(explanation, str) or not explanation.strip()
                or not isinstance(recommendations, list)
                or any(not isinstance(v, str) or not v.strip() for v in recommendations)):
            raise InvalidQualityOutput("invalid_explanation")
        restored = [pseudonymizer.restore(v) for v in [explanation, *recommendations]]
        if any(v.removed or not v.text.strip() for v in restored):
            raise InvalidQualityOutput("invalid_tokens")
        conclusions.append({**row, "code": code, "value": value, "explanation": restored[0].text,
                            "recommendations": [v.text for v in restored[1:]]})
        seen.add(code)
    return {"conclusions": conclusions}
