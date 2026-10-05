import { api, apiUpload } from "../../api/client";
import type { ApiConversation, ApiMessage, ConversationCounters, ConversationPriority, ConversationLabelRef, ReplyTemplateRef, WindowPage } from "./apiTypes";
import type { ListSort } from "./types";

export type ConversationListFilters = Partial<{
  group: string; // id | "none"
  agent: number; // id канала-агента
  assigned: "me" | number;
  waiting: boolean;
  queue: boolean;
  waitingOnMe: boolean;
  lifecycle: "OPEN" | "CLOSED" | "SPAM";
  archived: boolean;
  q: string;
}>;

// Запрос окна инбокса: фильтры, порядок и курсор — всё серверное.
export type ConversationListQuery = ConversationListFilters & {
  sort?: ListSort;
  cursor?: number | null;
  limit?: number;
};

export type ConversationWindow = WindowPage<ApiConversation> & { total: number };

export const fetchConversations = (query: ConversationListQuery = {}) => {
  const params = new URLSearchParams();
  if (query.group) params.set("group", query.group);
  if (query.agent) params.set("agent", String(query.agent));
  if (query.assigned) params.set("assigned", String(query.assigned));
  if (query.waiting) params.set("waiting", "1");
  if (query.queue) params.set("queue", "1");
  if (query.waitingOnMe) params.set("waitingOnMe", "1");
  if (query.lifecycle) params.set("lifecycle", query.lifecycle);
  if (query.archived) params.set("archived", "1");
  if (query.q) params.set("q", query.q);
  if (query.sort) params.set("sort", query.sort);
  if (query.cursor) params.set("cursor", String(query.cursor));
  if (query.limit) params.set("limit", String(query.limit));
  const suffix = params.size ? `?${params.toString()}` : "";
  return api<ConversationWindow>(`/api/v1/conversations/${suffix}`);
};

// Окно истории: без курсора — хвост переписки; before — вверх по ленте;
// after — то, что появилось после последнего показанного сообщения.
export type MessageWindowQuery = { before?: number | null; after?: number | null; limit?: number };

export const fetchMessages = (conversationId: number, query: MessageWindowQuery = {}) => {
  const params = new URLSearchParams();
  if (query.before) params.set("before", String(query.before));
  if (query.after) params.set("after", String(query.after));
  if (query.limit) params.set("limit", String(query.limit));
  const suffix = params.size ? `?${params.toString()}` : "";
  return api<WindowPage<ApiMessage>>(`/api/v1/conversations/${conversationId}/messages/${suffix}`);
};

export const fetchConversation = (id: number) => api<{ conversation: ApiConversation }>(`/api/v1/conversations/${id}/`).then((r) => r.conversation);
export const claimConversation = (id: number) => api<{ conversation: ApiConversation }>(`/api/v1/conversations/${id}/claim/`, { method: "POST" }).then((r) => r.conversation);
export const releaseConversation = (id: number) => api<{ conversation: ApiConversation }>(`/api/v1/conversations/${id}/release/`, { method: "POST" }).then((r) => r.conversation);
export const sendOperatorMessage = (id: number, text: string) => api(`/api/v1/conversations/${id}/messages/`, { method: "POST", body: JSON.stringify({ text }) });
export const returnToQueue = (id: number) => api<{ conversation: ApiConversation }>(`/api/v1/conversations/${id}/return-queue/`, { method: "POST" }).then((r) => r.conversation);
// Запрос контакта: в TG/MAX клиент видит кнопку «Поделиться контактом», в веб-чате — форму телефона.
export const requestContact = (id: number) => api(`/api/v1/conversations/${id}/request-contact/`, { method: "POST" });
export const closeConversation = (id: number) => api<{ conversation: ApiConversation }>(`/api/v1/conversations/${id}/close/`, { method: "POST" }).then((r) => r.conversation);
export const markConversationAsSpam = (id: number) => api<{ conversation: ApiConversation }>(`/api/v1/conversations/${id}/spam/`, { method: "POST" }).then((r) => r.conversation);
// Бейдж ожидающих диалогов. ConversationStatsView сейчас sales-only (SPEC §12:
// support-метрики — отдельный endpoint); department-параметр backend не использует.
export const fetchWaitingCount = () => api<{ waiting: number }>("/api/v1/conversations/stats/").then((r) => r.waiting);

// --- Дизайн-базлайн v2: карточка «Диалог», метки, шаблоны, счётчики ---

// Справочник блока «Диалог» (кадр G): все группы для переноса и коллеги для
// назначения — доступен и сотруднику, у которого нет менеджерских списков.
export type ChatDirectoryEmployee = {
  id: number;
  name: string;
  avatarUrl?: string | null;
  role?: string;
  /** Приложение открыто прямо сейчас. Признак приблизительный — см. Q5. */
  online?: boolean;
  lastSeenAt?: string | null;
  /** Сколько открытых диалогов уже на человеке: второй признак после присутствия. */
  openDialogs?: number;
};

export type ChatDirectory = {
  groups: Array<{ id: number; name: string; color?: string }>;
  // Выдача коллег ограничена, поиск — на сервере: ростер организации может
  // быть каким угодно, а выбор ответственного — не список.
  employees: ChatDirectoryEmployee[];
  hasMoreEmployees?: boolean;
};

// Карточка контакта из диалога (карандаш у имени, дизайн-базлайн v2).
export const updateContactCard = (conversationId: number, fields: Partial<{ name: string; description: string; phone: string; company: string; city: string }>) =>
  conversationAction(conversationId, "contact", fields);

export const fetchChatDirectory = (query = "") =>
  api<ChatDirectory>(`/api/v1/conversations/directory/${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`);

const conversationAction = (id: number, suffix: string, body: object) =>
  api<{ conversation: ApiConversation }>(`/api/v1/conversations/${id}/${suffix}/`, {
    method: "POST",
    body: JSON.stringify(body),
  }).then((r) => r.conversation);

export const setConversationPriority = (id: number, priority: ConversationPriority) =>
  conversationAction(id, "priority", { priority });
export const setConversationNote = (id: number, note: string) =>
  conversationAction(id, "note", { note });
export const setConversationLabels = (id: number, labelIds: number[]) =>
  conversationAction(id, "labels", { labelIds });
export const setConversationArchived = (id: number, archived: boolean) =>
  conversationAction(id, "archive", { archived });
/** Удалить диалог вместе с перепиской. Право — у владельца и администратора. */
export const deleteConversation = (id: number) =>
  api<void>(`/api/v1/conversations/${id}/`, { method: "DELETE" });
export const setConversationGroup = (id: number, groupId: number | null) =>
  conversationAction(id, "group", { groupId });
export const setConversationAssignee = (id: number, userId: number | null) =>
  conversationAction(id, "assignee", { userId });

export const fetchConversationCounters = () =>
  api<ConversationCounters>("/api/v1/conversations/counters/");
export const fetchConversationLabels = () =>
  api<{ items: ConversationLabelRef[] }>("/api/v1/conversations/labels/").then((r) => r.items);
export const createConversationLabel = (name: string, color = "") =>
  api<{ label: ConversationLabelRef }>("/api/v1/conversations/labels/", {
    method: "POST",
    body: JSON.stringify({ name, color }),
  }).then((r) => r.label);
export const fetchReplyTemplates = () =>
  api<{ items: ReplyTemplateRef[] }>("/api/v1/conversations/templates/").then((r) => r.items);
export const createReplyTemplate = (title: string, text: string) =>
  api<{ template: ReplyTemplateRef }>("/api/v1/conversations/templates/", {
    method: "POST",
    body: JSON.stringify({ title, text }),
  }).then((r) => r.template);
export const updateReplyTemplate = (id: number, title: string, text: string) =>
  api<{ template: ReplyTemplateRef }>(`/api/v1/conversations/templates/${id}/`, {
    method: "PATCH",
    body: JSON.stringify({ title, text }),
  }).then((r) => r.template);
export const deleteReplyTemplate = (id: number) =>
  api<void>(`/api/v1/conversations/templates/${id}/`, { method: "DELETE" });

export const transcribeMessage = (messageId: number) =>
  api<{ message: ApiMessage }>(`/api/v1/conversations/messages/${messageId}/transcribe/`, { method: "POST" }).then((r) => r.message);

export const sendVoiceMessage = (conversationId: number, audio: Blob, durationSeconds: number) => {
  const form = new FormData();
  const extension = audio.type.includes("ogg") ? "ogg" : audio.type.includes("webm") ? "webm" : "bin";
  form.append("audio", audio, `voice.${extension}`);
  form.append("duration", String(Math.round(durationSeconds)));
  return apiUpload<{ message: ApiMessage }>(`/api/v1/conversations/${conversationId}/voice/`, form).then((r) => r.message);
};

// Файл из композера («Прикрепить»): multipart file + подпись text.
export const sendFileMessage = (conversationId: number, file: File, caption: string) => {
  const form = new FormData();
  form.append("file", file, file.name);
  if (caption) form.append("text", caption);
  return apiUpload<{ message: ApiMessage }>(`/api/v1/conversations/${conversationId}/attachments/`, form).then((r) => r.message);
};

// --- Онлайн-звонки (SPEC-CHATBALLS-0013): запрос из диалога, ожидание, отмена ---

export type CallKind = "AUDIO" | "VIDEO";

export type ApiCall = {
  id: string;
  conversationId: number;
  status: "REQUESTED" | "RINGING" | "ACCEPTED" | "CONNECTING" | "ACTIVE" | "DECLINED" | "CANCELLED" | "MISSED" | "ENDED" | "FAILED" | "EXPIRED";
  kind: CallKind;
  requestedAt: string;
  acceptedAt: string | null;
  connectedAt: string | null;
  endedAt: string | null;
  endedBy: string | null;
  failureCode: string | null;
  durationSeconds: number | null;
};

export type CallAccess = { accessToken: string; iceServers: RTCIceServer[] };
export type CreatedCall = { call: ApiCall; access: CallAccess };

// Запрос звонка: при режиме AI backend атомарно выполняет takeover (§6).
export const requestCall = (conversationId: number, kind: CallKind = "AUDIO") =>
  api<{ call: ApiCall; staffAccessToken: string; iceServers: RTCIceServer[] }>(`/api/v1/calls/conversations/${conversationId}/`, { method: "POST", body: JSON.stringify({ kind }) })
    .then((r): CreatedCall => ({ call: r.call, access: { accessToken: r.staffAccessToken, iceServers: r.iceServers } }));
export const fetchActiveCall = (conversationId: number) =>
  api<{ call: ApiCall | null }>(`/api/v1/calls/conversations/${conversationId}/active/`).then((r) => r.call);
export const fetchCall = (callId: string) => api<{ call: ApiCall }>(`/api/v1/calls/${callId}/`).then((r) => r.call);
export const cancelCall = (callId: string) => api<{ call: ApiCall }>(`/api/v1/calls/${callId}/cancel/`, { method: "POST" }).then((r) => r.call);
export const fetchStaffCallAccess = (callId: string) =>
  api<{ accessToken: string; iceServers: RTCIceServer[] }>(`/api/v1/calls/${callId}/access-token/`, { method: "POST" });
export const endCallByAccess = (accessToken: string) =>
  api<{ call: ApiCall }>("/api/v1/calls/access/end/", { method: "POST", headers: { Authorization: `Bearer ${accessToken}` } }).then((r) => r.call);
