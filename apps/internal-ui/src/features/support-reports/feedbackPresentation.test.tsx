import { renderToStaticMarkup } from "react-dom/server";
import { beforeAll, describe, expect, it } from "vitest";
import { setPreLoginLanguage } from "../../i18n";
import { ReportQuality } from "./ReportQuality";
import { ReportRatings } from "./ReportRatings";
import { scoreLabel, versionPeriod } from "./feedbackPresentation";
import type { SupportReport } from "./types";

describe("feedback report presentation", () => {
  beforeAll(() => setPreLoginLanguage("ru"));
  it("renders the supplied mean and nulls, without calculating from distribution buckets", () => {
    const report = { employees: [], customerRatings: { scaleSummaries: [{
      scaleId: "snapshot", scale: [{ value: 1, label: "Low" }, { value: 5, label: "High" }],
      meanValue: 4.2, ratingCount: 10, commentCount: 0,
      distribution: [{ value: 1, label: "Low", count: 10, rate: 1 }],
      delivery: { sentCount: 0, answeredCount: 0, responseRate: null },
    }] } } as unknown as SupportReport;
    const html = renderToStaticMarkup(<ReportRatings report={report} employees={[]} />);
    expect(html).toContain("4,2 из 5");
    expect(html).toContain("ответили —");
    expect(html).toContain("Low");
  });
  it("renders an unused version with missing cells, retaining a genuine zero score in another version", () => {
    const base = { validFrom: "2026-10-14T10:00:00Z", validTo: null, correctionRate: 0, selectedJobCount: 1 };
    const criterion = { code: "a", name: "Criterion", description: "Description", scale: [0, 1, 2],
      scoredCount: 1, correctedCount: 0, missingCount: 0,
      originalSummary: { kind: "mean", value: 0 }, effectiveSummary: { kind: "mean", value: 0 } };
    const report = { period: { timezone: "UTC" }, qualityAnalysis: { versions: [
      { ...base, criteriaVersionId: 1, criteriaVersion: 1, analysisCount: 1, criteria: [criterion] },
      { ...base, criteriaVersionId: 2, criteriaVersion: 2, analysisCount: 0, criteria: [{ ...criterion,
        effectiveSummary: { kind: "mean", value: null }, correctedCount: null, missingCount: null }] },
    ] } } as unknown as SupportReport;
    const html = renderToStaticMarkup(<ReportQuality report={report} />);
    expect(html).toContain("версия 1");
    expect(html).toContain("версия 2");
    expect(html).toContain(">0</td>");
    expect(html).toContain("0 анализов в периоде");
    expect(html).toContain("is-missing");
    expect(scoreLabel({ kind: "unavailable", value: null })).toBe("—");
    expect(scoreLabel({ kind: "positiveRate", value: 0, positiveValue: "Yes" })).toContain("Yes");
  });
  it("formats version dates in the report timezone even when two versions were created in one millisecond", () => {
    expect(versionPeriod("2026-10-14T23:30:00Z", null, "Asia/Tokyo")).toContain("15");
    expect(() => versionPeriod("2026-10-14T10:00:00.000100Z", "2026-10-14T10:00:00.000200Z", "UTC")).not.toThrow();
  });
});
