import { api, apiUpload } from "../../api/client";
import type { EmailDraft, EmailOperation, EmailOptions, VisitorState } from "./emailTypes";

const path = (id: number) => `/api/v1/conversations/${id}/`;
export const fetchEmailOptions = (id: number) => api<EmailOptions>(`${path(id)}email/options/`);
export const fetchVisitorState = (id: number) => api<VisitorState>(`${path(id)}visitor-state/`);
export async function fetchEmailOperations(id: number, messageIds: number[]): Promise<{ items: EmailOperation[]; nextCursor: number | null }> {
  if (messageIds.length > 200) {
    const pages = await Promise.all(Array.from({ length: Math.ceil(messageIds.length / 200) }, (_, index) =>
      fetchEmailOperations(id, messageIds.slice(index * 200, (index + 1) * 200))));
    return { items: pages.flatMap((page) => page.items), nextCursor: null };
  }
  const query = messageIds.length ? `?messageIds=${messageIds.join(",")}&limit=200` : "";
  return api<{ items: EmailOperation[]; nextCursor: number | null }>(`${path(id)}email/operations/${query}`);
}
export async function sendEmail(id: number, draft: EmailDraft, clientKey: string) {
  if (!draft.file) return (await api<{ operation: EmailOperation }>(`${path(id)}email/operations/`, {
    method: "POST", body: JSON.stringify({ ...draft, file: undefined, clientKey }),
  })).operation;
  const form = new FormData();
  form.append("recipient", draft.recipient);
  form.append("connectionId", String(draft.connectionId));
  form.append("subject", draft.subject);
  form.append("text", draft.text);
  form.append("clientKey", clientKey);
  form.append("file", draft.file);
  return (await apiUpload<{ operation: EmailOperation }>(`${path(id)}email/operations/`, form)).operation;
}
export const retryEmail = (id: number, operation: EmailOperation) => api(`${path(id)}email/operations/${operation.id}/retry/`, {
  method: "POST", body: JSON.stringify({ acknowledgeUnknown: operation.attempts.some((attempt) => attempt.state === "UNKNOWN") }),
});
