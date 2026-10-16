import { describe, expect, it } from "vitest";

import { reconcileHistoryDelta } from "./historyDelta";
import type { ApiMessage } from "./apiTypes";

const msg = (id: number): ApiMessage => ({
  id, author: "AI", text: `message-${id}`, createdAt: "2026-10-12T12:00:00Z",
});

describe("reconcileHistoryDelta", () => {
  it("retracts an already rendered AI draft without adding a placeholder", () => {
    expect(reconcileHistoryDelta([msg(1), msg(2)], {
      items: [], cursor: null, hasMore: false, removedIds: [2],
    })).toEqual([msg(1)]);
  });
  it("keeps the new native reply while dropping its cancelled predecessor", () => {
    expect(reconcileHistoryDelta([msg(1), msg(2)], {
      items: [msg(3)], cursor: null, hasMore: false, removedIds: [2],
    })).toEqual([msg(1), msg(3)]);
  });
  it("deduplicates repeated deltas and preserves untouched messages", () => {
    const current = [msg(1), msg(2)];
    expect(reconcileHistoryDelta(current, {
      items: [msg(2)], cursor: null, hasMore: false,
    })).toEqual(current);
  });
  it("does not restore a retracted message from a late older window", () => {
    expect(reconcileHistoryDelta([msg(1), msg(3)], {
      items: [msg(2)], cursor: 1, hasMore: false,
    }, new Set([2]))).toEqual([msg(1), msg(3)]);
  });
});
