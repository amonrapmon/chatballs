import { describe, expect, it } from "vitest";
import { dayPeriods, initialFilters, midnight, periodQuery, reportPeriod } from "./period";

describe("report calendar boundaries", () => {
  it.each([
    ["2026-03-08", 23], ["2026-11-01", 25],
  ])("keeps the length of %s in New York at %s hours", (date, hours) => {
    const filters = { ...initialFilters("America/New_York"), start: date, end: date };
    const period = reportPeriod(filters);
    expect((Date.parse(period.to) - Date.parse(period.from)) / 3_600_000).toBe(hours);
    expect(period.timezone).toBe("America/New_York");
    expect(dayPeriods(filters)[0].period).toEqual(period);
  });
  it("uses the organization's calendar date instead of the browser date", () => {
    const filters = initialFilters("Pacific/Kiritimati", new Date("2026-10-13T12:00:00Z"));
    expect(filters.end).toBe("2026-10-14");
    expect(filters.start).toBe("2026-10-08");
    expect(midnight(filters.end, filters.timezone)).toBe("2026-10-13T10:00:00.000Z");
  });
  it("resolves a skipped midnight to the actual start of its local day", () => {
    expect(midnight("2018-11-04", "America/Sao_Paulo")).toBe("2018-11-04T03:00:00.000Z");
    expect(() => midnight("2011-12-30", "Pacific/Apia")).toThrow();
  });
  it("sends identical explicit dimensions to JSON and both file formats", () => {
    const filters = { ...initialFilters("Europe/Moscow"), start: "2026-10-01", end: "2026-10-07", employee: "4", group: "6", transport: "EMAIL", connection: "8" };
    const query = new URLSearchParams(periodQuery(reportPeriod(filters)));
    expect(Object.fromEntries(query)).toEqual({ from: "2026-09-30T21:00:00.000Z", to: "2026-10-07T21:00:00.000Z", timezone: "Europe/Moscow", employee: "4", group: "6", transport: "EMAIL", connection: "8" });
    expect(() => reportPeriod({ ...filters, start: "2026-10-08" })).toThrow();
  });
});
