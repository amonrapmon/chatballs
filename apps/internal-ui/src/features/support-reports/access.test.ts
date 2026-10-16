import { describe, expect, it } from "vitest";
import { allowedFilters, reportScopeKey } from "./access";
import { initialFilters } from "./period";
import type { ReportDirectory } from "./types";

const directory: ReportDirectory = { actions: ["reports.view", "reports.export"], restricted: true, revokedAt: null,
  groups: [{ id: 1, name: "Team" }], employees: [{ id: 2, fullName: "Member", email: "member@test", isBlocked: false }],
  connections: [{ id: 3, name: "Web", provider: "WEB" }], timezone: "UTC", timezones: ["UTC"] };
describe("current report area", () => {
  it("invalidates loaded results and export snapshots when grants or allowed identities change", () => {
    for (const change of [{ actions: [] }, { groups: [] }, { employees: [] }, { connections: [] }]) {
      expect(reportScopeKey({ ...directory, ...change })).not.toBe(reportScopeKey(directory));
    }
    expect(reportScopeKey({ ...directory, employees: [{ ...directory.employees[0], online: true }] })).toBe(reportScopeKey(directory));
  });
  it("drops revoked dimensions while preserving the period and other allowed filters", () => {
    const filters = { ...initialFilters("UTC"), employee: "2", group: "9", connection: "3", transport: "WEB" };
    expect(allowedFilters(filters, directory)).toEqual({ ...filters, group: "" });
    const allowed = { ...filters, group: "1" };
    expect(allowedFilters(allowed, directory)).toBe(allowed);
  });
});
