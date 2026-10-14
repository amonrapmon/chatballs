import type { CSSProperties } from "react";
import { fmt, t } from "../../i18n";
import { dateLabel, missing } from "./presentation";
import type { DayReport } from "./types";

export function ReportChart({ days }: { days: DayReport[] }) {
  const max = Math.max(1, ...days.flatMap(({ report }) => [report.totals.values.accepted ?? 0, report.totals.values.completed ?? 0]));
  return <section className="report-chart report-card">
    <div className="report-chart-heading"><h3>{t("reports.days")}</h3>
      <span><i className="report-legend accepted" />{t("reports.accepted")}</span>
      <span><i className="report-legend completed" />{t("reports.completed")}</span>
      <span><i className="report-legend is-current" />{t("reports.day_current")}</span>
    </div>
    <div className="report-chart-scroll"><div className="report-chart-days" style={{ "--report-days": days.length } as CSSProperties}>
      {days.map(({ date, report }) => {
        const label = dateLabel(date, report.period.timezone);
        const current = Date.parse(report.period.from) <= Date.parse(report.generatedAt) && Date.parse(report.generatedAt) < Date.parse(report.period.to);
        const counts = report.totals.values;
        const count = (value: number | null) => value === null ? missing : fmt.number(value);
        const title = t("reports.day_values", { date: label, accepted: count(counts.accepted), completed: count(counts.completed) });
        return <div key={date} className={current ? "report-chart-day is-current" : "report-chart-day"} title={title} aria-label={title}>
          <div className="report-bars">{(["accepted", "completed"] as const).map((key) => <span key={key} className={`report-bar ${key}${current ? " is-current" : ""}`} data-metric={key} data-value={counts[key] ?? ""}
            style={{ height: counts[key] === null ? undefined : `${counts[key]! / max * 150}px` }}>
            {counts[key] === null && <span className="is-missing">{missing}</span>}
          </span>)}</div>
          <small>{current ? t("reports.day_running", { date: label }) : label}</small>
        </div>;
      })}
    </div></div>
  </section>;
}
