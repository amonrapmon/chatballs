import { describe, expect, it } from "vitest";
import type { ApiMessage } from "./apiTypes";
import { conversationTimeline } from "./timeline";

const event = (id: number, turnId: number | null): ApiMessage => ({
  id, author: "SYSTEM", systemEvent: "tool_called", text: "", createdAt: "2026-10-05T17:02:00",
  toolCall: { tool: "Статус заказа", ok: true, errorCode: "", error: "", durationMs: 400, turnId },
});

describe("conversationTimeline", () => {
  it("groups the same turn across rounds and history deltas, preserving other rows", () => {
    const first = event(2, 1);
    const reply: ApiMessage = { id: 3, author: "AI", text: "Ответ", createdAt: first.createdAt };
    expect(conversationTimeline([first, reply])).toEqual([{ message: first, calls: [first.toolCall] }, { message: reply }]);
    const later = event(4, 1);
    const nextTurn = event(5, 3);
    expect(conversationTimeline([first, reply, later, nextTurn])).toEqual([
      { message: first, calls: [first.toolCall, later.toolCall] },
      { message: reply },
      { message: nextTurn, calls: [nextTurn.toolCall] },
    ]);
  });

  it("does not combine unknown turns or other system events", () => {
    const first = event(1, null);
    const second = event(2, null);
    const other = { ...event(3, 1), systemEvent: "operator_took" };
    const missing = { ...event(4, 1), toolCall: undefined };
    expect(conversationTimeline([first, second, other, missing])).toEqual([
      { message: first, calls: [first.toolCall] }, { message: second, calls: [second.toolCall] },
      { message: other }, { message: missing },
    ]);
  });
});
