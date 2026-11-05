import type { WindowPage } from "./apiTypes";

/** Apply additions and server-confirmed retractions from the same delta. */
export function reconcileHistoryDelta<T extends { id: number }>(
  current: T[],
  page: WindowPage<T> & { removedIds?: number[] },
  previouslyRemoved: ReadonlySet<number> = new Set(),
): T[] {
  const removed = new Set(previouslyRemoved);
  for (const id of page.removedIds ?? []) removed.add(id);
  const remaining = removed.size
    ? current.filter((message) => !removed.has(message.id))
    : current;
  const known = new Set(remaining.map((message) => message.id));
  const fresh = page.items.filter((message) => !known.has(message.id) && !removed.has(message.id));
  return fresh.length ? [...remaining, ...fresh] : remaining;
}
