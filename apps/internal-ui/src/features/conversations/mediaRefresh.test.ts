import { describe, expect, test } from "vitest";
import type { ApiMessage } from "./apiTypes";
import { mediaRefreshBatch } from "./mediaRefresh";

describe("staged Connector media refresh liveness", () => {
  const rows = Array.from({ length: 12 }, (_, index) => ({
    id: index + 1,
    mediaStatus: index % 2 === 0 ? "FAILED" : "PENDING"
  } as ApiMessage));

  test("checks every unresolved row eventually while bounding each poll to five", () => {
    let offset = 0;
    const seen = new Set<number>();
    for (let poll = 0; poll < 3; poll += 1) {
      const current = mediaRefreshBatch(rows, offset);
      expect(current.batch.length).toBeLessThanOrEqual(5);
      for (const row of current.batch) seen.add(row.id);
      offset = current.nextOffset;
    }
    expect(seen.size).toBe(12);
  });

  test("skips READY and legacy rows and handles changing unresolved counts", () => {
    const mixed = [
      { id: 1, mediaStatus: "READY" },
      { id: 2 },
      { id: 3, mediaStatus: "FAILED" },
    ] as ApiMessage[];
    expect(mediaRefreshBatch(mixed, 99).batch.map((row) => row.id)).toEqual([3]);
    expect(mediaRefreshBatch(mixed.slice(0, 2), 9)).toEqual({
      batch: [], nextOffset: 0
    });
  });
});
