"""One tabular projection of the API payload, used for all file formats."""

from chatballs.conversations.support_metrics import COUNTERS, DURATIONS
from chatballs.i18n import t


def _metric_rows(section, employee, name, metrics):
    for key in COUNTERS:
        yield [section, employee, name, key, t(f"support_stats.metric.{key}"),
               metrics["values"][key], metrics["observedCounts"][key],
               t("support_stats.unit.dialogs" if key in {"accepted", "completed"} else "support_stats.unit.events"),
               metrics["complete"], None, None]
    for key in DURATIONS:
        item = metrics["values"][key]
        yield [section, employee, name, key, t(f"support_stats.metric.{key}"),
               item["seconds"], item["observedSeconds"], t("support_stats.unit.seconds"),
               metrics["complete"], item["samples"], item["currentIntervals"]]
        if "meanSeconds" in item:
            yield [section, employee, name, key + ".mean", t(f"support_stats.metric.{key}") + " · " + t("support_stats.mean"),
                   item["meanSeconds"], None, t("support_stats.unit.seconds"),
                   metrics["complete"], item["samples"], item["currentIntervals"]]


def _status_rows(section, employee, name, statuses):
    for key, item in statuses["values"].items():
        yield [section, employee, name, "workStatus." + key, t(f"work_status.label.{key.lower()}"),
               item["seconds"], item["observedSeconds"], t("support_stats.unit.seconds"),
               statuses["complete"], None, item["currentIntervals"]]


def report_tables(report):
    metadata = [[t("support_stats.field"), t("support_stats.value")]]
    for key, value in report["period"].items():
        metadata.append([t(f"support_stats.filter.{key}"), value])
    metadata.extend([
        [t("support_stats.generated"), report["generatedAt"]],
        [t("support_stats.available"), report["coverage"]["availableFrom"]],
        [t("support_stats.complete"), report["coverage"]["complete"]],
        [t("support_stats.status_tracking"), report["coverage"]["statusStopsAvailableFrom"]],
        [t("support_stats.status_stop_policy"), t("support_stats.status_cut_at_block")],
        [t("support_stats.status_filter_scope"), t("support_stats.status_filter_scope_explanation")],
        [t("support_stats.missing"), ",".join(map(str, report["coverage"]["incompleteConversationIds"]))],
        [t("support_stats.null_marker"), t("support_stats.unavailable")],
        [t("support_stats.employee_overlap"), t("support_stats.employee_overlap_explanation")],
    ])
    header = [t(f"support_stats.column.{key}") for key in (
        "section", "employee", "name", "metric", "label", "value", "observed", "unit", "complete", "samples", "current",
    )]
    metrics = [header, *_metric_rows("totals", None, None, report["totals"])]
    metrics.extend(_status_rows("totals", None, None, report["workStatusTotals"]))
    metrics.append(["totals", None, None, "currentLoad", t("support_stats.load"), report["currentLoad"],
                    report["currentLoad"], t("support_stats.unit.dialogs"), True, None, None])
    for employee in report["employees"]:
        metrics.extend(_metric_rows("employee", employee["employee"], employee["name"], employee["metrics"]))
        metrics.extend(_status_rows("employee", employee["employee"], employee["name"], employee["workStatuses"]))
        metrics.append(["employee", employee["employee"], employee["name"], "currentLoad", t("support_stats.load"),
                        employee["currentLoad"], employee["currentLoad"], t("support_stats.unit.dialogs"), True, None, None])
    details = [[t(f"support_stats.column.{key}") for key in (
        "conversation", "metric", "employee", "group", "connection", "transport", "from", "to", "seconds", "current",
    )]]
    for detail in report["details"]:
        details.append([detail[key] for key in (
            "conversationId", "metric", "employee", "group", "connection", "transport", "from", "to", "seconds", "current",
        )])
    statuses = [[t(f"support_stats.column.{key}") for key in (
        "employee", "name", "included", "available", "complete", "blocked", "active", "blocked_at",
    )]]
    for employee in report["employees"]:
        status = employee["workStatuses"]
        statuses.append([employee["employee"], employee["name"], status["included"], status["availableFrom"],
                         status["complete"], employee["blocked"], employee["active"], status["blockedAt"]])
    status_details = [[t(f"support_stats.column.{key}") for key in (
        "employee", "status", "version", "from", "to", "seconds", "current",
    )]]
    for detail in report["workStatusDetails"]:
        status_details.append([detail[key] for key in ("employee", "status", "version", "from", "to", "seconds", "current")])
    return [("metadata", metadata), ("metrics", metrics), ("details", details),
            ("statuses", statuses), ("status_details", status_details)]
