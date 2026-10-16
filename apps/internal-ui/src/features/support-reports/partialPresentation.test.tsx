import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { t } from "../../i18n";
import { ReportChart } from "./ReportChart";
import { ReportEmployees } from "./ReportEmployees";
import { ReportMetrics } from "./ReportMetrics";
import { coverageTitle, durationLabel } from "./presentation";
import { countKeys, durationKeys, type Metrics, type SupportReport } from "./types";

function report(complete: boolean, accepted: number | null): SupportReport {
  const duration = { seconds: 120, observedSeconds: 120, samples: 2, currentIntervals: 0, meanSeconds: 60 };
  const metrics: Metrics = { complete,
    completeByMetric: Object.fromEntries([...countKeys, ...durationKeys].map(key => [key, complete])) as Metrics["completeByMetric"],
    observedCounts: Object.fromEntries(countKeys.map(key => [key, accepted ?? 0])) as Metrics["observedCounts"],
    values: { ...Object.fromEntries(countKeys.map(key => [key, accepted])),
      ...Object.fromEntries(durationKeys.map(key => [key, duration])) } as Metrics["values"],
  };
  return { period: { from: "2026-10-01T00:00:00Z", to: "2026-10-02T00:00:00Z", timezone: "UTC" },
    generatedAt: "2026-10-15T00:00:00Z", coverage: { complete, availableFrom: "2026-10-01T12:00:00Z" },
    totals: metrics, employees: [{ employee: 1, name: "Employee", metrics }], currentLoad: 0 } as SupportReport;
}

describe("partial history presentation", () => {
  it("shows available counts, intervals and means in cards and employee rows with coverage", () => {
    const value = report(false, 3);
    const tiles = renderToStaticMarkup(<ReportMetrics report={value} />);
    expect(tiles).toContain(t("reports.partial"));
    expect(tiles).toContain('data-metric="accepted"');
    expect(tiles).toContain('class="report-value">3</span>');
    expect(tiles).not.toContain(t("reports.unavailable"));
    const table = renderToStaticMarkup(<ReportEmployees report={value} employees={[]} />);
    expect(table).toContain('data-metric="accepted"><span class="report-value"');
    expect(table).toContain('>3</span>');
    expect(table).toContain(coverageTitle(value));
    expect(table).toContain(t("reports.partial"));
    expect(table).toContain(durationLabel(60));
  });
  it("retains unknown days, partial counts and known zero days in the same chart", () => {
    const html = renderToStaticMarkup(<ReportChart days={[
      { date: "2026-09-30", report: report(false, null) },
      { date: "2026-10-01", report: report(false, 3) },
      { date: "2026-10-02", report: report(true, 0) },
    ]} />);
    expect(html).toContain('data-value=""');
    expect(html).toContain('data-value="3"');
    expect(html).toContain('data-value="0"');
    expect(html).toContain(t("reports.partial"));
  });
  it("uses completeness of the metric rather than the entire period on cards", () => {
    const value = report(false, 0);
    countKeys.forEach(key => { value.totals.completeByMetric![key] = true; });
    const html = renderToStaticMarkup(<ReportMetrics report={value} />);
    const accepted = html.split('data-metric="accepted"')[1].split('data-metric="completed"')[0];
    expect(accepted).not.toContain('class="is-partial"');
    expect(accepted).toContain('class="report-value">0</span>');
    expect(html).toContain('class="is-partial"');
  });
});
