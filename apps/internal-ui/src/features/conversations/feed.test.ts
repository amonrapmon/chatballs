import { describe, expect, it } from "vitest";

import type { ApiMessage } from "./apiTypes";
import type { ApiComment } from "./commentApi";
import { conversationFeed, isOwnFeedRow, olderStream } from "./feed";

const at = (minute: number) => `2026-10-10T14:${String(minute).padStart(2, "0")}:00+00:00`;
const message = (id: number, minute: number, extra: Partial<ApiMessage> = {}): ApiMessage => ({ id, author: "CONTACT", text: `m${id}`, createdAt: at(minute), ...extra });
const comment = (id: number, minute: number, authorId = 7): ApiComment => ({
  id, conversationId: 1, audience: "INTERNAL", text: `c${id}`, author: { id: authorId, name: "Анна Ким" }, createdAt: at(minute), operationId: `op-${id}`,
});
const keys = (messages: ApiMessage[], comments: ApiComment[], older = { messages: false, comments: false }) =>
  conversationFeed({ items: messages, hasOlder: older.messages }, { items: comments, hasOlder: older.comments }).map((row) => row.key);

describe("лента диалога с внутренними комментариями", () => {
  it("ставит комментарии между сообщениями по времени, не путая одинаковые id", () => {
    expect(keys([message(1, 2), message(2, 6), message(3, 15)], [comment(1, 9), comment(2, 16)])).toEqual(["m1", "m2", "c1", "m3", "c2"]);
  });

  it("при равном времени показывает сообщение раньше комментария", () => {
    expect(keys([message(5, 9)], [comment(5, 9)])).toEqual(["m5", "c5"]);
  });

  it("не показывает строки раньше границы недогруженного окна", () => {
    const messages = [message(10, 20), message(11, 30)];
    const comments = [comment(1, 5), comment(2, 25)];
    expect(keys(messages, comments, { messages: true, comments: false })).toEqual(["m10", "c2", "m11"]);
    expect(keys(messages, comments)).toEqual(["c1", "m10", "c2", "m11"]);
    expect(keys([message(1, 1), ...messages], [comment(2, 25)], { messages: false, comments: true })).toEqual(["c2", "m11"]);
  });

  it("догружает то окно, которое держит границу", () => {
    const messages = { items: [message(10, 20)], hasOlder: true };
    const comments = { items: [comment(1, 25)], hasOlder: true };
    expect(olderStream(messages, comments)).toBe("comments");
    expect(olderStream(messages, { ...comments, items: [comment(1, 5)] })).toBe("messages");
    expect(olderStream(messages, { ...comments, hasOlder: false })).toBe("messages");
    expect(olderStream({ ...messages, hasOlder: false }, comments)).toBe("comments");
    expect(olderStream({ ...messages, hasOlder: false }, { ...comments, hasOlder: false })).toBeNull();
  });

  it("сохраняет группировку вызовов инструментов и отличает свои записи", () => {
    const call = (id: number): ApiMessage => message(id, 3, { author: "SYSTEM", systemEvent: "tool_called", toolCall: { tool: "Статус заказа", ok: true, errorCode: "", error: "", durationMs: 400, turnId: 1 } });
    const rows = conversationFeed(
      { items: [call(1), call(2), message(3, 4, { author: "OPERATOR", authorUserId: 7 })], hasOlder: false },
      { items: [comment(1, 5, 7), comment(2, 6, 8)], hasOlder: false },
    );
    expect(rows.map((row) => row.key)).toEqual(["m1", "m3", "c1", "c2"]);
    expect(rows[0].kind === "message" && rows[0].calls?.length).toBe(2);
    expect(rows.map((row) => isOwnFeedRow(row, 7))).toEqual([false, true, true, false]);
    expect(rows.some((row) => isOwnFeedRow(row, null))).toBe(false);
  });
});
