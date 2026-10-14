import { useEffect } from "react";
import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import { QualityCorrectionEditor } from "./QualityCorrectionEditor";
import { QualityEvidenceLinks } from "./QualityEvidenceLinks";
import { criterionName, scaleLabel, valueLabel } from "./presentation";
import type { QualityConclusion, QualityJob } from "./types";
import { useQualityCorrection } from "./useQualityCorrection";
import type { ReportQualityConflict } from "./QualityConflictBanner";

export function QualityConclusionCard({ job, conclusion, organizationId, accept, fail, reportConflict }: {
  job: QualityJob; conclusion: QualityConclusion; organizationId: string; accept: (job: QualityJob) => void; fail: (problem: unknown) => void;
  reportConflict: ReportQualityConflict;
}) {
  const state = useQualityCorrection(job, conclusion.code, conclusion.effectiveScaleIndex, accept, fail);
  useEffect(() => {
    const key = `${job.id}:${conclusion.code}`;
    reportConflict(state.conflict ? { key, job: state.conflict, showCurrent: state.showCurrent, cancel: state.cancel } : null, key);
    return () => reportConflict(null, key);
  }, [state.conflict, job.id, conclusion.code, reportConflict]);
  const criterion = job.criteria.find(row => row.code === conclusion.code);
  if (!criterion) return null;
  const latest = job.corrections.filter(row => row.criterionCode === conclusion.code).at(-1);
  return <section className={`quality-conclusion quality-card ${state.open ? "is-editing" : ""}`}>
    <header><div><h3>{criterionName(criterion)}</h3><small>{t("quality.scale_note", { description: criterion.description, scale: scaleLabel(criterion.scale) })}</small></div>
      <div className="quality-values">{latest && <><del title={t("quality.original")}>AI {valueLabel(conclusion.originalValue)}</del><Icon name="arrow" size={13} /></>}
        <b className={`quality-value ${latest ? "is-corrected" : ""}`} title={t(latest ? "quality.effective" : "quality.ai_value")}>{!latest && <Icon name="sparkles" size={13} />}{valueLabel(conclusion.effectiveValue)}</b>
        {!state.open && <Button variant="secondary" onClick={state.edit}>{t("quality.correct")}</Button>}</div>
    </header>
    {latest && <p className="quality-correction-note"><b>{latest.author?.name || t("common.operator")}, {fmt.shortDateTime(latest.createdAt)}:</b> {latest.reason}</p>}
    {state.open && <QualityCorrectionEditor criterion={criterion} state={state} />}
    <p className="quality-explanation">{conclusion.explanation}</p>
    {conclusion.recommendations.length > 0 && <div className="quality-recommendations"><b>{t("quality.recommendation")}</b>{conclusion.recommendations.map((advice, index) => <p key={index}>{advice}</p>)}</div>}
    <QualityEvidenceLinks evidence={conclusion.evidence} organizationId={organizationId} fail={fail} />
  </section>;
}
