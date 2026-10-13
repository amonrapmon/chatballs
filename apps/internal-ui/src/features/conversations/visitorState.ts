import type { VisitorObservation, VisitorState } from "./emailTypes";

export type VisitorSummary = { kind: "open" | "closed" | "hidden" | "lost" | "unknown"; since: string | null };
const newest = (rows: VisitorObservation[], field: "widgetChangedAt" | "pageChangedAt" | "connectionChangedAt") =>
  rows.map((row) => row[field]).filter((value): value is string => Boolean(value)).sort().at(-1) ?? null;

export function summarizeVisitor(state: VisitorState | null): VisitorSummary {
  const rows = state?.sessions.flatMap((session) => session.tabs) ?? [];
  // A document that fired pagehide left the screen (unloaded or in BFCache): it must not
  // mask the page the visitor sees now. Alone it proves nothing and stays uncertain.
  const active = rows.filter((row) => row.connection === "connected" && row.page !== "pagehide");
  const visible = active.filter((row) => row.page === "visible");
  if (visible.some((row) => row.widget === "open")) return { kind: "open", since: null };
  if (active.length && active.every((row) => row.page === "hidden")) return { kind: "hidden", since: newest(active, "pageChangedAt") };
  // Frozen and partially observed tabs remain uncertain.
  if (visible.length && visible.every((row) => row.widget === "closed") && active.every((row) => row.page === "visible" || row.page === "hidden")) {
    return { kind: "closed", since: newest(visible, "widgetChangedAt") };
  }
  if (rows.length && rows.every((row) => row.connection === "lost")) return { kind: "lost", since: newest(rows, "connectionChangedAt") };
  return { kind: "unknown", since: null };
}
