import { describe, expect, it } from "vitest";

import { t } from "../../i18n";
import type { ReplyAttempt, ReplySuggestion } from "./replyAssistanceApi";
import { availableVariants, draftMark, draftView } from "./replyDraft";

const suggestion = (position: number, patch: Partial<ReplySuggestion> = {}): ReplySuggestion => ({
  id: `s${position}`, attemptId: "a1", position, status: "READY", originalText: `Вариант ${position}`,
  errorCode: "", error: "", rejectedAt: null, sentMessageId: null, ...patch,
});
const attempt = (...suggestions: ReplySuggestion[]): ReplyAttempt => ({ id: "a1", suggestions });
const view = (value: ReplyAttempt | null, patch: Partial<Parameters<typeof draftView>[0]> = {}) =>
  draftView({ attempt: value, selectedId: null, dismissedId: null, requesting: false, requestError: "", ...patch });

describe("панель черновика", () => {
  it("закрыта, пока черновик не запрошен", () => {
    expect(view(null)).toBeNull();
  });

  it("показывает ожидание, пока сервер готовит первый вариант", () => {
    expect(view(null, { requesting: true })).toEqual({ kind: "loading" });
    expect(view(attempt(suggestion(1, { status: "PENDING", originalText: "" })))).toEqual({ kind: "loading" });
    expect(view(attempt(suggestion(1, { status: "RUNNING", originalText: "" })))).toEqual({ kind: "loading" });
  });

  it("показывает готовый вариант и держит прежний доступным, пока готовится другой", () => {
    expect(view(attempt(suggestion(1)))).toEqual({
      kind: "ready", variants: [{ id: "s1", text: "Вариант 1" }], selected: 0, rephrasing: false,
    });
    const rephrasing = view(attempt(suggestion(1), suggestion(2, { status: "RUNNING", originalText: "" })), { selectedId: "s1" });
    expect(rephrasing).toEqual({ kind: "ready", variants: [{ id: "s1", text: "Вариант 1" }], selected: 0, rephrasing: true });
  });

  it("переключает альтернативы по выбору оператора", () => {
    const three = attempt(suggestion(3), suggestion(1), suggestion(2));
    expect(view(three, { selectedId: "s2" })).toMatchObject({ kind: "ready", selected: 1 });
    expect(availableVariants(three).map((variant) => variant.id)).toEqual(["s1", "s2", "s3"]);
  });

  it("не предлагает отклонённые и отправленные варианты", () => {
    const decided = attempt(suggestion(1, { rejectedAt: "2026-10-12T10:00:00Z" }), suggestion(2, { sentMessageId: 7 }), suggestion(3));
    expect(availableVariants(decided)).toEqual([{ id: "s3", text: "Вариант 3" }]);
  });

  it("показывает причину ошибки и возвращается к вариантам после её закрытия", () => {
    const failed = attempt(suggestion(1), suggestion(2, { status: "ERROR", originalText: "", errorCode: "TIMEOUT", error: "Не удалось подготовить ответ." }));
    expect(view(failed)).toEqual({ kind: "error", reason: "Не удалось подготовить ответ." });
    expect(view(failed, { dismissedId: "s2" })).toMatchObject({ kind: "ready", selected: 0 });
    const silent = attempt(suggestion(1, { status: "ERROR", originalText: "", errorCode: "PROVIDER_UNAVAILABLE", error: "Не удалось подготовить ответ." }));
    expect(view(silent)).toEqual({ kind: "error", reason: t("conversations.draft_provider_silent") });
    expect(view(silent, { dismissedId: "s1" })).toBeNull();
  });

  it("показывает отказ сервера в самом запросе", () => {
    expect(view(null, { requestError: "Диалог недоступен" })).toEqual({ kind: "error", reason: "Диалог недоступен" });
  });
});

describe("метка вставленного черновика", () => {
  it("отличает нетронутый текст от изменённого", () => {
    expect(draftMark("Добрый день!", "Добрый день! ")).toBe(t("conversations.draft_mark"));
    expect(draftMark("Добрый день!", "Добрый день, Марина!")).toBe(t("conversations.draft_mark_edited"));
  });
});
