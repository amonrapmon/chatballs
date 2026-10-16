import { addDays, calendarDate } from "../support-reports/period";
import type { AuditPeriod } from "../administration/model";
import type { RuleExecution, RuleKind } from "./types";

export type DisplayStatus = RuleExecution["status"] | "CANCELLED";
export type JournalFilters = { kind: RuleKind | ""; status: DisplayStatus | ""; period: AuditPeriod; search: string };
export const emptyFilters: JournalFilters = { kind: "", status: "", period: "today", search: "" };
const cancelledReasons = new Set(["rule_disabled", "conversation_not_open", "assignment_removed", "assignment_replaced", "assignment_accepted", "not_waiting", "replied"]);

export const displayStatus = (entry: RuleExecution): DisplayStatus =>
  entry.status === "SKIPPED" && cancelledReasons.has(entry.reason) ? "CANCELLED" : entry.status;

export function matchesPeriod(entry: RuleExecution, period: AuditPeriod, timezone: string, now: Date): boolean {
  if (period === "all") return true;
  const today = calendarDate(now, timezone);
  const start = addDays(today, -(period === "today" ? 1 : parseInt(period, 10)) + 1);
  const date = calendarDate(new Date(entry.scheduledFor), timezone);
  return date >= start && date <= today;
}

export function filterJournal(entries: RuleExecution[], filters: JournalFilters, timezone: string, names: Record<number, string>, now = new Date()): RuleExecution[] {
  const search = filters.search.trim().toLocaleLowerCase();
  return entries.filter(entry => (!filters.kind || entry.rule.kind === filters.kind)
    && (!filters.status || displayStatus(entry) === filters.status)
    && matchesPeriod(entry, filters.period, timezone, now)
    && (!search || String(entry.conversationId).includes(search) || (names[entry.conversationId] ?? "").toLocaleLowerCase().includes(search)));
}
