import type { ApiConversation } from "./apiTypes";

export type SupervisionRevocation = { groupId: number; groupName: string; actorName: string; occurredAt: string };

export function supervisionRevocation(payload: Record<string, unknown>, previous: ApiConversation | null): SupervisionRevocation | null {
  const loss = payload.supervisionRevoked as Partial<SupervisionRevocation> | undefined;
  if (!previous?.access?.supervised || !loss || loss.groupId !== previous.group?.id
    || typeof loss.groupName !== "string" || typeof loss.actorName !== "string"
    || typeof loss.occurredAt !== "string" || !Number.isFinite(Date.parse(loss.occurredAt))) return null;
  return loss as SupervisionRevocation;
}

export function withoutConversationActions(previous: ApiConversation): ApiConversation {
  return { ...previous, access: { actions: [], supervised: false, isParticipant: false, canReply: false, canControl: false } };
}

export function conversationAction(detail: ApiConversation | null, action: string): boolean {
  return detail?.access?.actions.includes(action) ?? false;
}
