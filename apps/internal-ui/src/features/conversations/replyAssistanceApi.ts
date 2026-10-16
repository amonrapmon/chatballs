import { api } from "../../api/client";

// Помощь оператору: черновик ответа готовит агент, отправляет только человек.
// Сервер ведёт операцию в фоне; здесь — запрос, чтение состояния, отклонение и
// ручная отправка со ссылкой на выбранное предложение.

export type ReplySuggestionStatus = "PENDING" | "RUNNING" | "READY" | "ERROR";

export type ReplySuggestion = {
  id: string;
  attemptId: string;
  position: number;
  status: ReplySuggestionStatus;
  originalText: string;
  // Безопасный код причины; error — фраза сервера на языке читателя.
  errorCode: string;
  error: string;
  rejectedAt: string | null;
  sentMessageId: number | null;
};

export type ReplyAttempt = { id: string; suggestions: ReplySuggestion[] };

/** Ключ операции: повтор запроса с тем же ключом не порождает вторую операцию. */
export function operationKey(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  // randomUUID доступен только в защищённом контексте; на http без localhost — нет.
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

const conversationPath = (conversationId: number) => `/api/v1/conversations/${conversationId}`;

/** Новый черновик; с attemptId — другая формулировка в той же попытке. */
export const requestReplySuggestion = (conversationId: number, key: string, attemptId?: string) =>
  api<{ suggestion: ReplySuggestion }>(`${conversationPath(conversationId)}/reply-assistance/`, {
    method: "POST",
    body: JSON.stringify({ operationKey: key, ...(attemptId ? { attemptId } : {}) }),
  }).then((r) => r.suggestion);

export const fetchReplyAttempt = (conversationId: number, attemptId: string) =>
  api<{ attempt: ReplyAttempt }>(`${conversationPath(conversationId)}/reply-assistance/${attemptId}/`).then((r) => r.attempt);

export const rejectReplySuggestion = (conversationId: number, suggestionId: string) =>
  api<{ suggestion: ReplySuggestion }>(`${conversationPath(conversationId)}/reply-suggestions/${suggestionId}/reject/`, { method: "POST" }).then((r) => r.suggestion);

/** Ручная отправка: текст оператора уходит вместе со ссылкой на предложение. */
export const sendSuggestedReply = (conversationId: number, text: string, suggestionId: string, key: string) =>
  api(`${conversationPath(conversationId)}/messages/`, {
    method: "POST",
    body: JSON.stringify({ text, suggestionId, operationKey: key }),
  });
