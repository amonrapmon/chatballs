import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { durationLabel, metricDuration } from "../support-reports/presentation";
import { criterionName, valueLabel } from "./presentation";
import type { QualityJob } from "./types";

export function QualitySidebar({ job, jobs, select }: { job: QualityJob; jobs: QualityJob[]; select: (id: number) => void }) {
  const facts = job.temporalFacts;
  return <aside className="quality-sidebar">
    <section className="quality-card"><h3>{t("quality.times")}</h3><p className="quality-muted">{t("quality.times_note")}</p>
      {([ ["waiting", "quality.waiting_time"], ["firstResponse", "quality.first_response"], ["handling", "quality.handling"], ["subsequentResponse", "quality.subsequent_response"] ] as const).map(([key, label]) => {
        const value = facts ? metricDuration(facts.metrics, key) : null;
        return <div key={key}><div className="quality-time"><span>{t(label)}</span><b>{durationLabel(value)}</b></div>
          {value === null && facts?.availableFrom && <small className="quality-muted">{t("quality.missing_time", { date: fmt.shortDate(facts.availableFrom) })}</small>}</div>;
      })}
    </section>
    <section className="quality-card"><h3>{t("quality.history")}</h3>
      {!job.corrections.length && <p className="quality-muted">{t("quality.no_history")}</p>}
      {job.corrections.map((row, index) => {
        const criterion = job.criteria.find(item => item.code === row.criterionCode);
        const before = job.corrections.slice(0, index).filter(item => item.criterionCode === row.criterionCode).at(-1)?.value ?? job.conclusions.find(item => item.code === row.criterionCode)?.originalValue;
        const original = job.conclusions.find(item => item.code === row.criterionCode)?.originalValue;
        return <div className="quality-history-row" key={row.revision}><strong>{row.author?.name || t("common.operator")} · {criterion ? criterionName(criterion) : ""}</strong><small>{fmt.shortDateTime(row.createdAt)}</small>
          <p className="quality-history-values"><span>{t("quality.was", { value: before === undefined ? "—" : valueLabel(before) })}</span><Icon name="arrow" size={11} /><b>{t("quality.became", { value: valueLabel(row.value) })}</b><small>{t("quality.ai_original", { value: original === undefined ? "—" : valueLabel(original) })}</small></p><p>{row.reason}</p></div>;
      })}
    </section>
    <QualityRuns jobs={jobs} selectedId={job.id} select={select} />
  </aside>;
}

export function QualityRuns({ jobs, selectedId, select }: { jobs: QualityJob[]; selectedId: number | null; select: (id: number) => void }) {
  const labels = { WAITING: "quality.waiting", RUNNING: "quality.executing", SUCCEEDED: "quality.ready", FAILED: "quality.failed" } as const;
  return <section className="quality-card"><h3>{t("quality.runs")}</h3>{jobs.map(row => <div className="quality-run-row" key={row.id}>
    <div><button className={`link ${row.id === selectedId ? "is-strong" : "is-neutral"}`} onClick={() => select(row.id)}>{t("quality.run_title", { revision: fmt.number(row.revision), version: fmt.number(row.criteriaVersion) })}</button>
      <small>{row.startedAt ? fmt.shortDateTime(row.startedAt) : fmt.shortDateTime(row.completedAt)}</small></div><b className={`quality-chip is-${row.state.toLowerCase()}`}>{t(labels[row.state])}</b>
  </div>)}</section>;
}
