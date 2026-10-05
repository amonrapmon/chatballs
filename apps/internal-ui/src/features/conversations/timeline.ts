import type { ApiMessage } from "./apiTypes";

export type TimelineRow = { message: ApiMessage; calls?: NonNullable<ApiMessage["toolCall"]>[] };

/** Recomputed as history pages or realtime deltas arrive; keep the first event's position. */
export function conversationTimeline(messages: readonly ApiMessage[]): TimelineRow[] {
  const rows: TimelineRow[] = [];
  const turns = new Map<number, TimelineRow>();
  for (const message of messages) {
    if (message.author !== "SYSTEM" || message.systemEvent !== "tool_called" || !message.toolCall) {
      rows.push({ message });
      continue;
    }
    const call = message.toolCall;
    const existing = call.turnId == null ? undefined : turns.get(call.turnId);
    if (existing) {
      existing.calls!.push(call);
    } else {
      const row: TimelineRow = { message, calls: [call] };
      rows.push(row);
      if (call.turnId != null) turns.set(call.turnId, row);
    }
  }
  return rows;
}
