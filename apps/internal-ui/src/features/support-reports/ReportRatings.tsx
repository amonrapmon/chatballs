import { fmt, t, tn } from "../../i18n";
import type { Employee } from "../../types";
import { ReportEmployeeName } from "./ReportEmployeeName";
import { ReportTable } from "./ReportTable";
import { feedbackNumber, feedbackRate, scaleLabel } from "./feedbackPresentation";
import type { SupportReport } from "./types";

export function ReportRatings({ report, employees }: { report: SupportReport; employees: Employee[] }) {
  return <>{report.customerRatings.scaleSummaries.map((group) => {
    const scale = scaleLabel(group.scale.map((choice) => choice.value));
    return <div className="report-feedback-group" key={group.scaleId}>
      <ReportTable title={t("reports.rating_scale", { scale })} className="report-rating-distribution"
        badge={<b className="report-feedback-badge">{t("reports.rating_summary", {
          mean: feedbackNumber(group.meanValue), maximum: fmt.number(Math.max(...group.scale.map((choice) => choice.value))),
          count: tn("reports.rating_count", group.ratingCount, { count: fmt.number(group.ratingCount) }),
        })}</b>}
        side={t("reports.rating_delivery", { sent: fmt.number(group.delivery.sentCount), rate: feedbackRate(group.delivery.responseRate) })}
        headers={[t("reports.score"), t("reports.score_label"), t("reports.share"), t("reports.rating_counts")]}
        foot={t("reports.rating_scale_note")}>
        {[...group.distribution].reverse().map((bucket) => <tr key={bucket.value}>
          <td><strong>{fmt.number(bucket.value)}</strong></td><td>{bucket.label}</td>
          <td><span className="report-rating-bar" title={feedbackRate(bucket.rate)}>{bucket.rate !== null && <i style={{ width: `${bucket.rate * 100}%` }} />}</span></td>
          <td>{fmt.number(bucket.count)}</td>
        </tr>)}
      </ReportTable>
      <ReportTable title={t("reports.employees")} side={t("reports.rating_scale", { scale })} className="report-rating-employees"
        headers={[t("reports.employee"), t("reports.mean"), t("reports.rating_counts"), t("reports.with_comment")]}
        foot={t("reports.rating_responders_note")}>
        {report.employees.map((row) => {
          const own = row.customerRatings.scaleSummaries.find((item) => item.scaleId === group.scaleId);
          const available = own && own.ratingCount > 0;
          return <tr key={row.employee}><td><ReportEmployeeName row={row} employee={employees.find((item) => item.id === row.employee)} /></td>
            <td className={available ? "" : "is-missing"} title={available ? undefined : t("reports.no_ratings")}>{feedbackNumber(own?.meanValue ?? null)}</td>
            <td className={available ? "" : "is-missing"}>{feedbackNumber(available ? own.ratingCount : null)}</td>
            <td className={available ? "" : "is-missing"}>{feedbackNumber(available ? own.commentCount : null)}</td></tr>;
        })}
      </ReportTable>
    </div>;
  })}</>;
}
