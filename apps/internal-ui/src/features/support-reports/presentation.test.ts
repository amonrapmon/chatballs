import { describe, expect, it } from "vitest";
import { dateLabel, durationLabel, emptyPeriod, metricDuration } from "./presentation";
import { countKeys, durationKeys, type Metrics, type SupportReport } from "./types";

function metrics(): Metrics {
  return {
    complete: true,
    observedCounts: Object.fromEntries(countKeys.map((key) => [key, 0])) as Metrics["observedCounts"],
    values: {
      ...Object.fromEntries(countKeys.map((key) => [key, 0])),
      ...Object.fromEntries(durationKeys.map((key) => [key, { seconds: 0, observedSeconds: 0, samples: 0, currentIntervals: 0, ...(key.endsWith("Response") ? { meanSeconds: null } : {}) }])),
    } as Metrics["values"],
  };
}

describe("support report presentation", () => {
  it("preserves sums, means and nulls without turning observed values into complete values", () => {
    const data = metrics();
    data.values.handling = { seconds: 300, observedSeconds: 300, samples: 3, currentIntervals: 1 };
    data.values.firstResponse = { seconds: 120, observedSeconds: 120, samples: 3, meanSeconds: 40, currentIntervals: 0 };
    expect(metricDuration(data, "handling")).toBe(300);
    expect(metricDuration(data, "firstResponse")).toBe(40);
    data.complete = false;
    data.values.handling.seconds = null;
    data.values.firstResponse.meanSeconds = null;
    expect(metricDuration(data, "handling")).toBeNull();
    expect(metricDuration(data, "firstResponse")).toBeNull();
    expect(durationLabel(null)).toBe("—");
    expect(durationLabel(0)).not.toBe("—");
  });
  it("does not call missing history empty even when all observed counters are zero", () => {
    const report = { totals: metrics(), coverage: { complete: true } } as SupportReport;
    expect(emptyPeriod(report)).toBe(true);
    report.coverage.complete = false;
    expect(emptyPeriod(report)).toBe(false);
    report.coverage.complete = true;
    report.totals.values.waiting.samples = 1;
    expect(emptyPeriod(report)).toBe(false);
  });
  it("shows the selected calendar date unchanged in UTC+14", () => {
    expect(dateLabel("2026-10-14", "Pacific/Kiritimati")).toBe(dateLabel("2026-10-14", "UTC"));
  });
});
