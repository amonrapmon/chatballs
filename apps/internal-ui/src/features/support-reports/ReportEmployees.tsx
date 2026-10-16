import { t } from "../../i18n";
import type { ReportStaff } from "./types";
import { coverageTitle, metricComplete, metricDuration } from "./presentation";
import { ReportEmployeeName } from "./ReportEmployeeName";
import { ReportTable } from "./ReportTable";
import { ReportValue } from "./ReportValue";
import type { SupportReport } from "./types";

export function ReportEmployees({ report, employees }: { report: SupportReport; employees: ReportStaff[] }) {
  const partialTitle = `${t("reports.partial")} · ${coverageTitle(report)}`;
  const rows = [...report.employees].sort((a, b) => b.metrics.observedCounts.accepted - a.metrics.observedCounts.accepted || a.employee - b.employee);
  const headers = [t("reports.employee"), t("reports.accepted"), t("reports.completed"), t("reports.sent"), t("reports.waiting_column"), t("reports.handling_column"), t("reports.firstResponse"), t("reports.subsequent_column")];
  return <ReportTable title={t("reports.employees")} side={t("reports.sort")} headers={headers} foot={t("reports.no_value_foot")} className="report-employees">
    {rows.map((row) => <tr key={row.employee} data-employee={row.employee}>
      <td><ReportEmployeeName row={row} employee={employees.find((item) => item.id === row.employee)} /></td>
      {(["accepted", "completed", "transferred"] as const).map((key) => <td key={key} data-metric={key}><ReportValue value={row.metrics.values[key]} title={!metricComplete(row.metrics, key) ? partialTitle : undefined} /></td>)}
      {(["waiting", "handling", "firstResponse", "subsequentResponse"] as const).map((key) => <td key={key} data-metric={key} title={t(key.endsWith("Response") ? "reports.duration_mean" : "reports.duration_total")}>
        <ReportValue value={metricDuration(row.metrics, key)} duration title={!metricComplete(row.metrics, key) ? partialTitle : undefined} />
      </td>)}
    </tr>)}
  </ReportTable>;
}
