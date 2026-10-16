import { describe, expect, it } from "vitest";
import { changesFor, validateRule } from "./model";
import { displayStatus, emptyFilters, filterJournal } from "./journalModel";
import type { HandlingRule, RuleExecution } from "./types";

const rule: HandlingRule = {
  kind: "WAIT_EXCEEDED_NOTICE", enabled: false, version: 1, delayMinutes: 10, text: "", conditions: {}, recipients: [], updatedAt: null, updatedBy: "",
  catalog: { conditions: ["channelIds", "availableOnly"], recipients: ["CONVERSATION_GROUP"], requiresText: false, maxDelayMinutes: 1440, maxTextLength: 1000, deadlinePlaceholder: "" },
};

describe("handling rule settings", () => {
  it("sends only fields changed in the selected rule, without its version or catalogue", () => {
    expect(changesFor(rule, { ...rule, enabled: true, recipients: ["CONVERSATION_GROUP"] })).toEqual({ enabled: true, recipients: ["CONVERSATION_GROUP"] });
    expect(changesFor(rule, rule)).toEqual({});
  });
  it("requires recipients and text when enabled, while allowing incomplete disabled rules", () => {
    expect(validateRule(rule)).toEqual({});
    expect(validateRule({ ...rule, enabled: true })).toHaveProperty("recipients");
    const receipt = { ...rule, enabled: true, catalog: { ...rule.catalog, recipients: [], requiresText: true } };
    expect(validateRule(receipt)).toHaveProperty("text");
  });
  it("keeps delay integral and within the server limit", () => {
    for (const delayMinutes of [0, -1, 1.5, 1441, NaN]) expect(validateRule({ ...rule, delayMinutes })).toHaveProperty("delayMinutes");
    expect(validateRule({ ...rule, delayMinutes: 1440 })).toEqual({});
  });
});

function execution(id: number, scheduledFor: string, reason = ""): RuleExecution {
  return { id, conversationId: id, rule: { kind: "REPLY_REMINDER", version: 1 }, action: "REPLY_REMINDER", sourceEvent: { id, type: "PUBLIC_REPLY", occurredAt: scheduledFor },
    startedAt: scheduledFor, scheduledFor, finishedAt: null, status: reason ? "SKIPPED" : "PENDING", reason, reasonLabel: "", attempts: 0, recipients: [], messageId: null, notificationId: null };
}

describe("scoped handling rule journal presentation", () => {
  it("distinguishes cancellation from skipped conditions and errors", () => {
    expect(displayStatus(execution(1, "2026-10-13T21:00:00Z", "replied"))).toBe("CANCELLED");
    expect(displayStatus(execution(1, "2026-10-13T21:00:00Z", "no_recipients"))).toBe("SKIPPED");
    expect(displayStatus({ ...execution(1, "2026-10-13T21:00:00Z"), status: "FAILED" })).toBe("FAILED");
  });
  it("filters the organization's calendar day across UTC midnight", () => {
    const items = [execution(1, "2026-10-13T20:59:59Z"), execution(2, "2026-10-13T21:00:00Z"), execution(3, "2026-10-14T21:00:00Z")];
    expect(filterJournal(items, emptyFilters, "Europe/Moscow", {}, new Date("2026-10-14T12:00:00Z")).map(item => item.id)).toEqual([2]);
  });
  it("combines local filters and searches only names from accessible details", () => {
    const items = [execution(21, "2026-10-14T12:00:00Z", "replied"), execution(22, "2026-10-14T12:00:00Z", "no_recipients")];
    const filters = { ...emptyFilters, period: "all" as const, status: "CANCELLED" as const, search: "Мария" };
    expect(filterJournal(items, filters, "Europe/Moscow", { 21: "Мария" }).map(item => item.id)).toEqual([21]);
    expect(filterJournal(items, filters, "Europe/Moscow", {})).toEqual([]);
  });
});
