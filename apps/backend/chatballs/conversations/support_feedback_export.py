"""Feedback tables project calculated data without reading source models."""

import json

from chatballs.i18n import t


def _value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _table(columns):
    return [[t(f"support_stats.feedback.{key}") for key in columns]]


def feedback_tables(report):
    summaries = _table(("section", "employee", "source", "state", "count", "period", "policy", "states"))
    rating_columns = ("id", "requestId", "conversationId", "completionId", "responderIds", "scale", "value",
                      "comment", "receivedAt", "group", "connection", "transport")
    rating_details = _table(rating_columns)
    rating_groups = _table(("section", "employee", "scaleId", "scale", "count", "value", "valueCount"))
    quality_columns = ("id", "conversationId", "completionEventId", "completedAt", "revision", "historyRevision",
                       "criteriaVersionId", "criteriaVersion", "responderIds", "state", "errorCode",
                       "correctionRevision", "conclusions", "group", "connection", "transport")
    quality_details = _table(quality_columns)
    quality_groups = _table(("section", "employee", "criteriaVersionId", "criteriaVersion", "code", "scale",
                            "count", "source", "value", "valueCount"))
    sections = [("totals", None, report), *[("employee", row["employee"], row) for row in report["employees"]]]
    for section, employee, data in sections:
        for source in ("customerRatings", "qualityAnalysis"):
            item = data[source]
            summaries.append([section, employee, source, item["state"], item["count"], item["periodBasis"],
                              item.get("revisionPolicy"), _value(item.get("states"))])
        for group in data["customerRatings"]["groups"]:
            for value, count in group["values"].items():
                rating_groups.append([section, employee, group["scaleId"], _value(group["scale"]),
                                      group["count"], int(value), count])
        for group in data["qualityAnalysis"]["groups"]:
            for source in ("originalValues", "effectiveValues"):
                for bucket in group[source]:
                    quality_groups.append([section, employee, group["criteriaVersionId"], group["criteriaVersion"],
                                           group["code"], _value(group["scale"]), group["count"], source,
                                           bucket["value"], bucket["count"]])
    # Details occur once in exports; responderIds carry the overlapping staff attribution.
    for row in report["customerRatings"]["details"]:
        rating_details.append([_value(row[key]) for key in rating_columns])
    for row in report["qualityAnalysis"]["details"]:
        quality_details.append([_value(row[key]) for key in quality_columns])
    return [("feedback_summary", summaries), ("rating_groups", rating_groups), ("rating_details", rating_details),
            ("quality_groups", quality_groups), ("quality_details", quality_details)]
