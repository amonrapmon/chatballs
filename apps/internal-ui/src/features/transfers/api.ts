import { api, ApiError } from "../../api/client";
import { t } from "../../i18n";
import type { PagedPayload } from "../../shared/usePagedResource";

export type WorkStatus = "READY" | "BUSY" | "BREAK" | "UNAVAILABLE";
export type AssignmentPolicy = Record<WorkStatus, boolean>;
export type TransferReason = {
  id: number; code: string; name: string; isActive: boolean; usageCount: number;
  previousName: string; renamedAt: string | null;
};
export type TransferReasonOption = Pick<TransferReason, "id" | "code" | "name" | "isActive">;
type Person = { id: number; name: string; avatarUrl: string | null } | null;
export type TransferRecord = {
  id: number; operationId: string; occurredAt: string; initiatedBy: Person;
  previousOperator: Person; newOperator: Person;
  reason: { id: number; name: string; isActive: boolean; currentName: string };
  comment: string;
  conversation: { contactName: string; provider: string };
};
export type TransferInput = {
  userId: number; reasonId: number; comment: string; expectedVersion: number; operationId: string;
};
const base = "/api/v1/conversations";
export const fetchReasons = (page: number) =>
  api<PagedPayload<TransferReason>>(`${base}/transfer-reasons/?page=${page}`);
export const saveReason = (name: string, id?: number) =>
  api<{ reason: TransferReason }>(`${base}/transfer-reasons/${id ? `${id}/` : ""}`, {
    method: id ? "PATCH" : "POST", body: JSON.stringify({ name }),
  });
export const toggleReason = (id: number, active: boolean) =>
  api(`${base}/transfer-reasons/${id}/`, active
    ? { method: "PATCH", body: JSON.stringify({ isActive: true }) }
    : { method: "DELETE" });
export const fetchPolicy = () =>
  api<{ allowedStatuses: AssignmentPolicy | null }>(`${base}/assignment-policy/`);
export const savePolicy = (policy: AssignmentPolicy) =>
  api<{ allowedStatuses: AssignmentPolicy }>(`${base}/assignment-policy/`, {
    method: "PUT", body: JSON.stringify(policy),
  });
export const fetchTransferOptions = (id: number, page: number) =>
  api<PagedPayload<TransferReasonOption>>(`${base}/${id}/transfer-options/?page=${page}&pageSize=100`);
export const fetchTransfers = (id: number, page = 1) =>
  api<PagedPayload<TransferRecord>>(`${base}/${id}/transfers/?page=${page}`);
export const transferConversation = (id: number, input: TransferInput) =>
  api<{ transfer: { id: number; operationId: string } }>(`${base}/${id}/assignee/`, {
    method: "POST", body: JSON.stringify(input),
  });
export const fetchTransfer = (conversationId: number, transferId: number) =>
  api<{ transfer: TransferRecord }>(`${base}/${conversationId}/transfers/${transferId}/`);

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    const strings = (value: unknown): string[] => typeof value === "string" ? [value]
      : Array.isArray(value) ? value.flatMap(strings)
      : value && typeof value === "object" ? Object.values(value).flatMap(strings) : [];
    return strings(error.payload).join(" ");
  }
  return error instanceof TypeError ? t("shared.network_error")
    : error instanceof Error ? error.message : t("common.request_failed");
}
