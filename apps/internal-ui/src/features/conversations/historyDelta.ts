import type { ApiMessage } from "./apiTypes";
import type { MessageWindow } from "./conversationApi";

/** Apply additions and server-confirmed retractions from the same delta. */
export function reconcileHistoryDelta(current: ApiMessage[], page: MessageWindow): ApiMessage[] {
  const removed = new Set(page.removedIds ?? []);
  const remaining = removed.size
    ? current.filter((message) => !removed.has(message.id))
    : current;
  const known = new Set(remaining.map((message) => message.id));
  const fresh = page.items.filter((message) => !known.has(message.id) && !removed.has(message.id));
  return fresh.length ? [...remaining, ...fresh] : remaining;
}
