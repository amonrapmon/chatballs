import type { ApiMessage } from "./apiTypes";

const MAX_STATUS_READS = 5;

export function mediaRefreshBatch(
  items: readonly ApiMessage[], offset: number,
): { batch: ApiMessage[]; nextOffset: number } {
  const unresolved = items.filter((row) => row.mediaStatus === "PENDING" || row.mediaStatus === "FAILED");
  const count = unresolved.length;
  if (count === 0) return { batch: [], nextOffset: 0 };
  const start = Math.max(0, offset) % count;
  const size = Math.min(count, MAX_STATUS_READS);
  const batch = Array.from({ length: size }, (_, index) => unresolved[(start + index) % count]!);
  return { batch, nextOffset: (start + size) % count };
}
