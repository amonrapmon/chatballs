import { api } from "../../api/client";
import type { PagedPayload } from "../../shared/usePagedResource";

export type ActivityFilter = "all" | "transfers" | "participants";
type Actor = { id: number | null; name: string } | null;
export type ActivityRecord = {
  id: string; kind: "TRANSFER" | "JOIN" | "LEAVE" | "CLAIM"; occurredAt: string;
  actor: Actor; recipient: Actor; comment: string;
  reason: { name: string; isActive?: boolean; currentName?: string } | null;
};

export const fetchActivity = (conversationId: number, kind: ActivityFilter, page: number) =>
  api<PagedPayload<ActivityRecord>>(`/api/v1/conversations/${conversationId}/activity-history/?kind=${kind}&page=${page}&pageSize=5`);
