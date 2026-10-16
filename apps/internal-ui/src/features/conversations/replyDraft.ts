import { t } from "../../i18n";
import type { ReplyAttempt, ReplySuggestion } from "./replyAssistanceApi";

// Что показывает панель черновика (макет «Чат · состояния», кадры A2–A8).
// Состояние выводится из попытки целиком: панель не хранит своей копии текста.

export type DraftVariant = { id: string; text: string };

export type DraftView =
  | { kind: "loading" }
  | { kind: "ready"; variants: DraftVariant[]; selected: number; rephrasing: boolean }
  | { kind: "error"; reason: string };

export const isPending = (suggestion: ReplySuggestion) =>
  suggestion.status === "PENDING" || suggestion.status === "RUNNING";

const byPosition = (attempt: ReplyAttempt) =>
  [...attempt.suggestions].sort((left, right) => left.position - right.position);

/** Варианты, которые ещё можно вставить: готовые, не отклонённые и не отправленные. */
export function availableVariants(attempt: ReplyAttempt | null): DraftVariant[] {
  if (!attempt) return [];
  return byPosition(attempt)
    .filter((suggestion) => suggestion.status === "READY" && !suggestion.rejectedAt && suggestion.sentMessageId == null)
    .map((suggestion) => ({ id: suggestion.id, text: suggestion.originalText }));
}

/** Сбой последнего запроса в попытке, пока его не закрыли. */
export function failedSuggestion(attempt: ReplyAttempt | null, dismissedId: string | null): ReplySuggestion | null {
  const latest = attempt ? byPosition(attempt).at(-1) : undefined;
  return latest && latest.status === "ERROR" && latest.id !== dismissedId ? latest : null;
}

export function failureReason(suggestion: ReplySuggestion): string {
  if (suggestion.errorCode === "PROVIDER_UNAVAILABLE" || !suggestion.error) return t("conversations.draft_provider_silent");
  return suggestion.error;
}

export function draftView({ attempt, selectedId, dismissedId, requesting, requestError }: {
  attempt: ReplyAttempt | null;
  selectedId: string | null;
  /** Закрытая оператором ошибка: панель возвращается к готовым вариантам. */
  dismissedId: string | null;
  /** Запрос ушёл, сервер ещё не подтвердил операцию. */
  requesting: boolean;
  /** Сервер отказал в самом запросе — операции нет. */
  requestError: string;
}): DraftView | null {
  if (requestError) return { kind: "error", reason: requestError };
  const failed = failedSuggestion(attempt, dismissedId);
  if (failed) return { kind: "error", reason: failureReason(failed) };
  const variants = availableVariants(attempt);
  const pending = requesting || Boolean(attempt?.suggestions.some(isPending));
  if (variants.length === 0) return pending ? { kind: "loading" } : null;
  const index = variants.findIndex((variant) => variant.id === selectedId);
  return { kind: "ready", variants, selected: index === -1 ? variants.length - 1 : index, rephrasing: pending };
}

/** Метка у текста, вставленного из черновика (кадр A6). */
export function draftMark(originalText: string, text: string): string {
  return text.trim() === originalText.trim() ? t("conversations.draft_mark") : t("conversations.draft_mark_edited");
}
