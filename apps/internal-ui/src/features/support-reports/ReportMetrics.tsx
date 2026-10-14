import { t } from "../../i18n";
import { coverageTitle, metricDuration } from "./presentation";
import { ReportValue } from "./ReportValue";
import type { SupportReport } from "./types";

export function ReportMetrics({ report }: { report: SupportReport | null }) {
  const values = report?.totals.values;
  const tiles = [
    { key: "accepted", value: values?.accepted ?? null, note: t("reports.accepted_note") },
    { key: "completed", value: values?.completed ?? null, note: t("reports.completed_note") },
    { key: "transferred", value: values?.transferred ?? null, note: t("reports.transferred_note") },
    ...(["waiting", "handling", "firstResponse", "subsequentResponse"] as const).map((key) => ({
      key, value: report ? metricDuration(report.totals, key) : null, duration: true,
      note: t(key.endsWith("Response") ? "reports.duration_mean" : "reports.duration_total"),
    })),
    { key: "currentLoad", value: report?.currentLoad ?? null, note: t("reports.load_note") },
  ] as const;
  return <div className="report-metrics" aria-busy={!report}>{tiles.map((tile) => {
    const partial = report && tile.key !== "currentLoad" && !report.coverage.complete;
    return <div className="report-tile" key={tile.key} data-metric={tile.key} title={partial ? coverageTitle(report) : undefined}>
      <span className="report-tile-label">{t(`reports.${tile.key}`)}
        {tile.key === "currentLoad" && <b>{t("reports.now")}</b>}
        {partial && <b className="is-partial">{t("reports.partial")}</b>}
      </span>
      {!report ? <><i className="report-skeleton" /><i className="report-skeleton is-small" /></> : <>
        <strong><ReportValue value={tile.value} duration={"duration" in tile} /></strong>
        <small>{partial ? t("reports.unavailable") : tile.note}</small>
      </>}
    </div>;
  })}</div>;
}
