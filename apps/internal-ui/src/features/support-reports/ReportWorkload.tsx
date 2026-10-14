import type { CSSProperties } from "react";
import { t } from "../../i18n";
import type { Employee } from "../../types";
import { DirectoryWorkStatus } from "../work-status/WorkStatusLabel";
import { statusLabel, workStatusCodes, type WorkStatusCode } from "../work-status/model";
import { durationLabel, instantLabel, timeLabel } from "./presentation";
import { ReportEmployeeName } from "./ReportEmployeeName";
import { ReportTable } from "./ReportTable";
import { ReportValue } from "./ReportValue";
import type { ReportEmployee, SupportReport } from "./types";

const statusColors: Record<WorkStatusCode, string> = { READY: "var(--success)", BUSY: "var(--error)", BREAK: "var(--warning)", UNAVAILABLE: "var(--n-6)" };

function StatusBar({ row }: { row: ReportEmployee }) {
  const values = row.workStatuses.values;
  const total = workStatusCodes.reduce((sum, key) => sum + values[key].observedSeconds, 0);
  if (!row.workStatuses.included || total === 0) return <ReportValue value={row.workStatuses.complete ? 0 : null} duration />;
  return <span className="report-status-bar" title={!row.workStatuses.complete ? t("reports.partial") : undefined}>
    {workStatusCodes.map((key) => <i key={key} className={values[key].currentIntervals > 0 ? "is-current" : ""}
      data-status={key} data-seconds={values[key].observedSeconds}
      title={`${statusLabel(key)} · ${durationLabel(values[key].seconds)}${values[key].currentIntervals ? ` · ${t("reports.interval_running")}` : ""}`}
      style={{ width: `${values[key].observedSeconds / total * 100}%`, "--status-color": statusColors[key] } as CSSProperties} />)}
  </span>;
}

export function ReportWorkload({ report, employees, waiting }: { report: SupportReport; employees: Employee[]; waiting: Record<number, number> }) {
  const employee = (id: number) => employees.find((item) => item.id === id);
  return <>
    <ReportTable title={t("reports.load_title")} side={t("reports.updated", { time: timeLabel(report.generatedAt, report.period.timezone) })}
      headers={[t("reports.employee"), t("reports.work_status"), t("reports.open_dialogs"), t("reports.waiting_replies")]}
      foot={t("reports.presence_note")} className="report-load">
      {report.employees.map((row) => <tr key={row.employee} data-employee={row.employee}>
        <td><ReportEmployeeName row={row} employee={employee(row.employee)} presence /></td>
        <td><DirectoryWorkStatus value={employee(row.employee)?.workStatus} online={employee(row.employee)?.online} /></td>
        <td data-metric="currentLoad"><ReportValue value={row.currentLoad} /></td>
        <td data-metric="waitingReplies"><ReportValue value={waiting[row.employee] ?? 0} /></td>
      </tr>)}
    </ReportTable>
    <ReportTable title={t("reports.status_time")} side={t("reports.status_period")}
      headers={[t("reports.employee"), t("reports.distribution"), t("reports.total")]}
      className="report-statuses" foot={t("reports.no_value_foot")}
      legend={workStatusCodes.map((key) => <span key={key}><i style={{ background: statusColors[key] }} />{statusLabel(key, true)}</span>)}>
      {report.employees.map((row) => {
        const status = row.workStatuses;
        const total = status.complete && status.included ? workStatusCodes.reduce((sum, key) => sum + (status.values[key].seconds ?? 0), 0) : null;
        const current = report.workStatusDetails.find((item) => item.employee === row.employee && item.current);
        return <tr key={row.employee} data-employee={row.employee}>
          <td><ReportEmployeeName row={row} employee={employee(row.employee)} /></td>
          <td><StatusBar row={row} />{!status.complete && <small className="report-status-coverage">{t("reports.partial")}{status.availableFrom ? ` · ${t("reports.available_since", { date: instantLabel(status.availableFrom, report.period.timezone) })}` : ""}</small>}</td>
          <td><ReportValue value={total} duration />{current && <small>{t("reports.status_running", { status: statusLabel(current.status, true), time: timeLabel(current.from, report.period.timezone) })}</small>}</td>
        </tr>;
      })}
    </ReportTable>
  </>;
}
