import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { t } from "../../i18n";
import { correctionCommand, correctionDraft, reduceCorrection, type CorrectionDraft } from "./correctionModel";
import { QualityConclusionCard } from "./QualityConclusionCard";
import { QualityConflictBanner } from "./QualityConflictBanner";
import { QualityCorrectionEditor } from "./QualityCorrectionEditor";
import { QualityEvidenceList } from "./QualityEvidenceList";
import { QualitySidebar } from "./QualitySidebar";
import type { QualityJob } from "./types";

// Isolated unit input; never installed in the application or a backend database.
function analysis(): QualityJob {
  const counts = { accepted: 0, completed: 1, transferred: 0, receivedTransfers: 0, humanReplies: 1, aiReplies: 0 };
  const duration = { seconds: null, observedSeconds: 0, samples: 0, currentIntervals: 0, meanSeconds: null };
  return {
    id: 12, conversationId: 31, criteriaVersion: 1, revision: 1, historyRevision: "history",
    completionEventId: "00000000-0000-0000-0000-000000000001", completedAt: "2026-10-12T15:52:00Z",
    state: "SUCCEEDED", errorCode: null, startedAt: "2026-10-12T15:52:00Z", finishedAt: "2026-10-12T15:52:10Z", resultId: 20,
    criteria: [{ code: "resolution", name: "Решение вопроса", description: "Вопрос решён", scale: [1, 2, 3, 4, 5] }],
    conclusions: [{ code: "resolution", originalValue: 4, effectiveValue: 4, effectiveScaleIndex: 3,
      explanation: "Клиенту отправлен чек.", recommendations: ["Уточните, нужно ли что-то ещё."],
      evidence: [{ messageId: 134, url: "/api/v1/conversations/quality/jobs/12/messages/134/" }], evidenceAvailable: true }],
    correctionRevision: 0, corrections: [], temporalFacts: { state: "missing_history", availableFrom: "2026-10-08T00:00:00Z",
      metrics: { complete: false, observedCounts: counts, values: { ...counts, waiting: duration, handling: duration,
        firstResponse: duration, subsequentResponse: duration, aiResponse: duration } } },
  };
}
function corrected(original: QualityJob): QualityJob {
  return { ...original, correctionRevision: 1,
    conclusions: [{ ...original.conclusions[0], effectiveValue: 5, effectiveScaleIndex: 4 }],
    corrections: [{ revision: 1, criterionCode: "resolution", value: 5, reason: "Клиент подтвердил получение.",
      author: { membershipId: 2, userId: 2, name: "Анна Ким" }, createdAt: "2026-10-13T07:20:00Z" }],
  };
}
const noop = () => undefined;
function editorState(state: CorrectionDraft) {
  return { ...state, setValue: noop, setReason: noop, edit: noop, cancel: noop, save: async () => undefined, showCurrent: noop };
}

describe("supervisor correction workflow", () => {
  it("requires a nonblank reason and blocks closed or busy editors", () => {
    const closed = correctionDraft(0, 3);
    expect(correctionCommand(closed, 12, "resolution")).toBeNull();
    const open = reduceCorrection(closed, { type: "edit", revision: 0, value: 4 });
    expect(correctionCommand({ ...open, reason: " \n " }, 12, "resolution")).toBeNull();
    const ready = reduceCorrection(open, { type: "reason", reason: "Проверено" });
    expect(correctionCommand(ready, 12, "resolution")?.scaleIndex).toBe(4);
    expect(correctionCommand(reduceCorrection(ready, { type: "start" }), 12, "resolution")).toBeNull();
  });
  it("keeps the original result and draft after a conflict until explicit review", () => {
    const original = analysis();
    const unchanged = JSON.stringify(original);
    const current = corrected(original);
    let draft = reduceCorrection(correctionDraft(0, 3), { type: "edit", revision: 0, value: 2 });
    draft = reduceCorrection(draft, { type: "reason", reason: "Моё пояснение" });
    expect(correctionCommand(draft, original.id, "resolution")?.expectedRevision).toBe(0);
    draft = reduceCorrection(draft, { type: "conflict", job: current });
    expect(correctionCommand(draft, original.id, "resolution")).toBeNull();
    expect([draft.value, draft.reason, draft.revision]).toEqual([2, "Моё пояснение", 0]);
    const reviewed = reduceCorrection(draft, { type: "showCurrent", code: "resolution" });
    expect(correctionCommand(reviewed, original.id, "resolution")).toMatchObject({ expectedRevision: 1, scaleIndex: 4, reason: "Моё пояснение" });
    expect(correctionCommand(reduceCorrection(draft, { type: "cancel" }), original.id, "resolution")).toBeNull();
    expect(JSON.stringify(original)).toBe(unchanged);
    expect(current.conclusions[0].originalValue).toBe(4);
  });
});

describe("baseline quality views", () => {
  it("renders original and effective values, explanation, recommendations and server review history separately", () => {
    const job = corrected(analysis());
    const before = JSON.stringify(job);
    const card = renderToStaticMarkup(<QualityConclusionCard job={job} conclusion={job.conclusions[0]} organizationId="org"
      accept={noop} fail={noop} reportConflict={noop} />);
    expect(card).toContain(`<del title="${t("quality.original")}">AI 4</del>`);
    expect(card).toContain(`title="${t("quality.effective")}">5</b>`);
    expect(card).toContain("Клиенту отправлен чек.");
    expect(card).toContain("Уточните, нужно ли что-то ещё.");
    expect(card).toContain("Анна Ким");
    expect(card).toContain("Клиент подтвердил получение.");
    expect(card).toContain("1–5");
    const history = renderToStaticMarkup(<QualitySidebar job={job} jobs={[job]} select={noop} />);
    expect(history).toContain(t("quality.history"));
    expect(history).toContain(t("quality.ai_original", { value: "4" }));
    expect(history).toContain(t("quality.became", { value: "5" }));
    expect(history).toContain("Клиент подтвердил получение.");
    expect(history).toContain("—");
    expect(JSON.stringify(job)).toBe(before);
  });
  it("renders the mandatory reason state and explicit actions for a conflicting review", () => {
    const job = analysis();
    const required = { ...correctionDraft(0, 3), open: true, required: true };
    const editor = renderToStaticMarkup(<QualityCorrectionEditor criterion={job.criteria[0]} state={editorState(required)} />);
    expect(editor).toContain('aria-invalid="true"');
    expect(editor).toContain(t("quality.reason_required"));
    const banner = renderToStaticMarkup(<QualityConflictBanner conflict={{ key: "12:resolution", job: corrected(job), showCurrent: noop, cancel: noop }} />);
    expect(banner).toContain("Анна Ким");
    expect(banner).toContain(t("quality.show_current"));
    expect(banner).toContain(t("quality.cancel_correction"));
  });
  it("links an authorized evidence message to the tenant conversation and exact message anchor", () => {
    const organizationId = "12345678-1234-1234-1234-123456789abc";
    const markup = renderToStaticMarkup(<QualityEvidenceList organizationId={organizationId} messages={[
      { messageId: 134, conversationId: 31, authorType: "CONTACT", createdAt: "2026-10-12T15:52:00Z", text: "Спасибо, получила!", contentHtml: "", transcript: "" },
    ]} />);
    expect(markup).toContain(`href="/organizations/${organizationId}/chat?conversation=31#message-134"`);
    expect(markup).toContain("Спасибо, получила!");
    expect(markup).toContain('class="link is-muted has-icon"');
  });
});
