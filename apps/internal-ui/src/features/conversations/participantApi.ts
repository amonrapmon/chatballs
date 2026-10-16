import { api } from "../../api/client";

export type ParticipantLimit = {
  additionalParticipantLimit: number;
  updatedAt: string | null;
  updatedBy: string;
};

export const fetchParticipantLimit = () =>
  api<ParticipantLimit>("/api/v1/conversations/participant-limit/");

export const saveParticipantLimit = (additionalParticipantLimit: number) =>
  api<ParticipantLimit>("/api/v1/conversations/participant-limit/", {
    method: "PATCH", body: JSON.stringify({ additionalParticipantLimit }),
  });

import type { WorkStatus } from "../work-status/model";

export type ParticipantMember = { membershipId: number; userId: number; name: string; avatarUrl: string | null };
export type ApiParticipant = {
  id: number; membershipId: number; userId: number;
  member: ParticipantMember; joinedBy: ParticipantMember; leftBy: ParticipantMember | null;
  joinedAt: string; joinReason: string; leftAt: string | null; leaveReason: string;
  online?: boolean; workStatus?: WorkStatus;
};
export type ParticipantRoster = { items: ApiParticipant[]; additionalParticipantLimit: number };
export const fetchParticipants = (id: number) => api<ParticipantRoster>(`/api/v1/conversations/${id}/participants/`);
export const addParticipant = (id: number, membershipId: number, reason: string) =>
  api<{ participant: ApiParticipant }>(`/api/v1/conversations/${id}/participants/`, { method: "POST", body: JSON.stringify({ membershipId, reason }) });
export const removeParticipant = (id: number, participantId: number, reason: string) =>
  api<{ participant: ApiParticipant }>(`/api/v1/conversations/${id}/participants/${participantId}/`, { method: "DELETE", body: JSON.stringify({ reason }) });
export type JournalKind = "all" | "transfers" | "participants";
export type JournalEntry = {
  id: string; kind: "JOINED" | "LEFT" | "TRANSFER"; occurredAt: string;
  actorName: string; subjectName: string; reason: string; comment: string;
  reasonChanged: boolean; reasonInactive: boolean;
};
export type JournalPage = { items: JournalEntry[]; page: number; pageSize: number; pageCount: number; total: number };
export const fetchParticipationJournal = (id: number, kind: JournalKind = "all", page = 1, pageSize = 20) =>
  api<JournalPage>(`/api/v1/conversations/${id}/participation-journal/?kind=${kind}&page=${page}&pageSize=${pageSize}`);
