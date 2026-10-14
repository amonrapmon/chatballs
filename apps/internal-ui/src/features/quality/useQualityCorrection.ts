import { useReducer } from "react";
import { ApiError } from "../../api/client";
import { t } from "../../i18n";
import { correctQuality, fetchQualityJob } from "./api";
import type { QualityJob } from "./types";
import { correctionCommand, correctionDraft, reduceCorrection } from "./correctionModel";

export function useQualityCorrection(job: QualityJob, code: string, initialValue: number | null, accept: (job: QualityJob) => void, fail: (problem: unknown) => void) {
  const [state, dispatch] = useReducer(reduceCorrection, correctionDraft(job.correctionRevision, initialValue));
  function edit() { dispatch({ type: "edit", revision: job.correctionRevision, value: initialValue }); }
  function cancel() { dispatch({ type: "cancel" }); }
  async function save() {
    const command = correctionCommand(state, job.id, code);
    if (!command) { if (state.open && !state.busy && !state.conflict && !state.reason.trim()) dispatch({ type: "required" }); return; }
    dispatch({ type: "start" });
    try { accept(await correctQuality(command.jobId, command.expectedRevision, command.criterionCode, command.scaleIndex, command.reason)); cancel(); }
    catch (problem) {
      if (problem instanceof ApiError && problem.status === 409) {
        try { const current = await fetchQualityJob(job.id); accept(current); dispatch({ type: "conflict", job: current }); }
        catch (refreshProblem) { fail(refreshProblem); }
      } else if (problem instanceof ApiError && [403, 404].includes(problem.status)) fail(problem);
      else dispatch({ type: "error", error: problem instanceof Error ? problem.message : t("common.request_failed") });
    } finally { dispatch({ type: "finish" }); }
  }
  function showCurrent() {
    dispatch({ type: "showCurrent", code });
  }
  return { ...state, setValue: (value: number) => dispatch({ type: "value", value }),
    setReason: (reason: string) => dispatch({ type: "reason", reason }), edit, cancel, save, showCurrent };
}
