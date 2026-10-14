import { fmt, t, tn } from "../../i18n";
import { ReportTable } from "./ReportTable";
import { feedbackNumber, feedbackRate, scaleLabel, scoreLabel, versionPeriod } from "./feedbackPresentation";
import type { SupportReport } from "./types";

export function ReportQuality({ report }: { report: SupportReport }) {
  return <>{report.qualityAnalysis.versions.map((version) => <ReportTable key={version.criteriaVersionId}
    title={t("reports.criteria_version", { version: fmt.number(version.criteriaVersion) })}
    className={`report-quality${version.analysisCount === 0 ? " is-empty-version" : ""}`}
    badge={<b className={`report-feedback-badge${version.analysisCount === 0 ? " is-muted" : ""}`}>
      {versionPeriod(version.validFrom, version.validTo, report.period.timezone)} · {tn(version.analysisCount ? "reports.analysis_count" : "reports.empty_analysis_count", version.analysisCount, { count: fmt.number(version.analysisCount) })}
    </b>}
    side={version.analysisCount ? t("reports.quality_effective", { rate: feedbackRate(version.correctionRate) }) : undefined}
    headers={[t("reports.criterion"), t("reports.scale"), t("reports.mean"), t("reports.corrected"), t("reports.unscored")]}
    foot={version.analysisCount ? t("reports.unscored_note") : t("reports.versions_note")}>
    {version.criteria.map((criterion) => <tr key={criterion.code}>
      <td title={criterion.description}><strong>{criterion.name}</strong></td><td>{scaleLabel(criterion.scale)}</td>
      <td className={criterion.effectiveSummary.value === null ? "is-missing" : ""} title={version.analysisCount === 0 ? t("reports.no_version_analyses") : undefined}>{scoreLabel(criterion.effectiveSummary)}</td>
      <td className={criterion.correctedCount === null ? "is-missing" : ""}>{feedbackNumber(criterion.correctedCount)}</td>
      <td className={criterion.missingCount === null ? "is-missing" : ""}>{feedbackNumber(criterion.missingCount)}</td>
    </tr>)}
  </ReportTable>)}</>;
}
