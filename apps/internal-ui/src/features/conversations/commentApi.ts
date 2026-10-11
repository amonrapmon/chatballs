import { api } from "../../api/client";
import type { WindowPage } from "./apiTypes";
import { windowSuffix, type MessageWindowQuery } from "./conversationApi";

// Внутренний комментарий — не сообщение клиенту: свой endpoint, свои
// идентификаторы и свой курсор. Через маршрут сообщений он не создаётся и не
// читается, поэтому ответ клиенту и комментарий не пересекаются уже на уровне
// запроса.
export type ApiComment = {
  id: number;
  conversationId: number;
  audience: "INTERNAL";
  text: string;
  author: { id: number; name: string; avatarUrl?: string | null };
  createdAt: string;
  operationId: string;
};

const commentsPath = (conversationId: number) => `/api/v1/conversations/${conversationId}/comments/`;

export const fetchComments = (conversationId: number, query: MessageWindowQuery = {}) =>
  api<WindowPage<ApiComment>>(`${commentsPath(conversationId)}${windowSuffix(query)}`);

/** operationId — ключ идемпотентности: повтор той же отправки вернёт ту же запись. */
export const createComment = (conversationId: number, text: string, operationId: string) =>
  api<{ comment: ApiComment }>(commentsPath(conversationId), {
    method: "POST",
    body: JSON.stringify({ audience: "INTERNAL", text, operationId }),
  }).then((r) => r.comment);
