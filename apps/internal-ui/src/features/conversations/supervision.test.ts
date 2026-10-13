import { describe, expect, it } from "vitest";
import type { ApiConversation } from "./apiTypes";
import { conversationAction, supervisionRevocation, withoutConversationActions } from "./supervision";

const detail = { id: 4, group: { id: 8, name: "Support" }, access: {
  actions: ["conversations.view", "conversations.assign", "conversations.comment"],
  supervised: true, canReply: false, canControl: false, isParticipant: false,
} } as ApiConversation;
const loss = { groupId: 8, groupName: "Support", actorName: "Admin", occurredAt: "2026-10-13T12:00:00Z" };

describe("server supervision access", () => {
  it("uses effective actions and disables every action after revocation", () => {
    expect(conversationAction(detail, "conversations.assign")).toBe(true);
    expect(conversationAction(detail, "conversations.operate")).toBe(false);
    const revoked = withoutConversationActions(detail);
    expect(revoked.access?.actions).toEqual([]);
    expect(revoked.access?.canReply).toBe(false);
    expect(revoked.access?.canControl).toBe(false);
    expect(detail.access?.supervised).toBe(true);
  });
  it("shows only the server loss for the previously supervised group", () => {
    expect(supervisionRevocation({ supervisionRevoked: loss }, detail)).toEqual(loss);
    expect(supervisionRevocation({ supervisionRevoked: { ...loss, groupId: 9 } }, detail)).toBeNull();
    expect(supervisionRevocation({ supervisionRevoked: loss }, withoutConversationActions(detail))).toBeNull();
    expect(supervisionRevocation({ supervisionRevoked: { ...loss, occurredAt: "invalid" } }, detail)).toBeNull();
  });
});
