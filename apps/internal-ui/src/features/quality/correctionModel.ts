import type { QualityJob } from "./types";

export type CorrectionDraft = {
  open: boolean; value: number | null; reason: string; revision: number; busy: boolean;
  required: boolean; error: string; conflict: QualityJob | null;
};
export type CorrectionAction =
  | { type: "edit"; revision: number; value: number | null }
  | { type: "value"; value: number }
  | { type: "reason"; reason: string }
  | { type: "required" }
  | { type: "start" }
  | { type: "finish" }
  | { type: "cancel" }
  | { type: "error"; error: string }
  | { type: "conflict"; job: QualityJob }
  | { type: "showCurrent"; code: string };

export const correctionDraft = (revision: number, value: number | null): CorrectionDraft => ({
  open: false, value, reason: "", revision, busy: false, required: false, error: "", conflict: null,
});

export function reduceCorrection(state: CorrectionDraft, action: CorrectionAction): CorrectionDraft {
  switch (action.type) {
    case "edit": return { ...correctionDraft(action.revision, action.value), open: true };
    case "value": return { ...state, value: action.value };
    case "reason": return { ...state, reason: action.reason };
    case "required": return { ...state, required: true };
    case "start": return { ...state, busy: true, error: "", required: false };
    case "finish": return { ...state, busy: false };
    case "cancel": return { ...state, open: false, conflict: null, error: "" };
    case "error": return { ...state, error: action.error };
    case "conflict": return { ...state, conflict: action.job };
    case "showCurrent": return state.conflict ? {
      ...state, revision: state.conflict.correctionRevision,
      value: state.conflict.conclusions.find(row => row.code === action.code)?.effectiveScaleIndex ?? null,
      conflict: null,
    } : state;
  }
}

export function correctionCommand(state: CorrectionDraft, jobId: number, code: string) {
  if (!state.open || state.busy || state.conflict || state.value === null || !state.reason.trim()) return null;
  return { jobId, expectedRevision: state.revision, criterionCode: code, scaleIndex: state.value, reason: state.reason };
}
