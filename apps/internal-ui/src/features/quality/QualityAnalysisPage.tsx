import { useCallback, useState } from "react";
import { isManager } from "../../auth/access";
import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { ContentState, LoadingState } from "../../shared/ui";
import { Button } from "../../shared/ui-controls";
import type { SessionUser } from "../../types";
import { conversationName } from "../conversations/model";
import { QualityConclusionCard } from "./QualityConclusionCard";
import { QualityBanner } from "./QualityBanner";
import { QualityConflictBanner, type QualityConflict, type ReportQualityConflict } from "./QualityConflictBanner";
import { QualityRuns, QualitySidebar } from "./QualitySidebar";
import { useQualityAnalysis } from "./useQualityAnalysis";
import "./analysis.css";

export function QualityAnalysisPage({ id, user, back }: { id: number; user: SessionUser; back: () => void }) {
  const canLaunch = isManager(user);
  const state = useQualityAnalysis(id, canLaunch);
  const [conflict, setConflict] = useState<QualityConflict | null>(null);
  const reportConflict = useCallback<ReportQualityConflict>((view, key) => setConflict(current => view || (current?.key === key ? null : current)), []);
  const { job, jobs, conversation } = state;
  const latest = jobs[0];
  const pending = latest && ["WAITING", "RUNNING"].includes(latest.state);
  const preserved = job?.state === "SUCCEEDED" && latest?.id !== job.id;
  if (!state.loaded) return <LoadingState />;
  if (state.denied) return <ContentState icon={<Icon name="lock" size={21} />} title={t("shared.403_access_denied")} text={state.error} />;
  return <div className="quality-analysis">
    <button className="link is-muted has-icon quality-back" onClick={back}><Icon name="chevronLeft" size={14} />{conversation ? t("quality.dialog_back", { name: conversationName(conversation), date: fmt.shortDate(conversation.createdAt) }) : t("common.chat")}</button>
    <header className="quality-page-heading"><div><h2>{t("quality.title")}</h2><p>{conversation?.channel.name}{conversation?.group ? ` · ${conversation.group.name}` : ""}</p>
      <div className="quality-heading-chips">{(job?.criteriaVersion || state.settings?.criteriaVersion) && <b className="quality-chip is-version">{t("quality.criteria_version", { version: fmt.number(job?.criteriaVersion || state.settings!.criteriaVersion!) })}</b>}
        {job && <b className="quality-chip">{preserved && pending ? t("quality.run_until", { revision: fmt.number(job.revision), next: fmt.number(latest.revision) }) : t("quality.run_date", { revision: fmt.number(job.revision), date: fmt.shortDateTime(job.finishedAt || job.completedAt) })}</b>}</div></div>
      {canLaunch && <Button variant={jobs.length ? "secondary" : "primary"} icon={jobs.length ? "refresh" : "sparkles"} disabled={state.busy || Boolean(pending)} onClick={() => void state.launch()}>{t(pending || state.busy ? "quality.running" : jobs.length ? "quality.repeat" : "quality.launch")}</Button>}
    </header>
    {state.error && <p className="quality-error" role="alert">{state.error}</p>}
    {conflict && <QualityConflictBanner conflict={conflict} />}
    {pending && <QualityBanner tone="info" title={t("quality.running_title", { version: fmt.number(latest.criteriaVersion) })}
      text={preserved ? t("quality.running_note", { revision: fmt.number(job.revision) }) : t("quality.running")} />}
    {latest?.state === "FAILED" && <QualityBanner tone="error" title={t("quality.failed_title", { revision: fmt.number(latest.revision) })}
      text={`${t(latest.errorCode === "provider_unavailable" ? "quality.provider_failed" : "quality.invalid_result")} ${preserved ? t("quality.previous_remains", { revision: fmt.number(job.revision) }) : ""}`}
      actions={canLaunch && <Button variant="secondary" disabled={state.busy} onClick={() => void state.launch()}>{t("common.try_again")}</Button>} />}
    {!job && <ContentState icon={<Icon name="info" size={21} />} title={t("quality.empty")} text={t("quality.empty_note")} />}
    {job?.state === "SUCCEEDED" && <div className={`quality-results ${preserved && pending ? "is-pending" : ""}`}><main className="quality-conclusions">
      {job.conclusions.map(conclusion => <QualityConclusionCard key={`${job.id}:${conclusion.code}`} job={job} conclusion={conclusion} organizationId={user.organizationPublicId} accept={state.accept} fail={state.fail} reportConflict={reportConflict} />)}</main>
      <QualitySidebar job={job} jobs={jobs} select={state.select} /></div>}
    {job && job.state !== "SUCCEEDED" && <QualityRuns jobs={jobs} selectedId={job.id} select={state.select} />}
  </div>;
}
