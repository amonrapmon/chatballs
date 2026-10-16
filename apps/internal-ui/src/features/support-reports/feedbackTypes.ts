export type RatingScaleSummary = {
  scaleId: string; scale: Array<{ value: number; label: string }>;
  ratingCount: number; meanValue: number | null; commentCount: number;
  distribution: Array<{ value: number; label: string; count: number; rate: number | null }>;
  delivery: { sentCount: number; answeredCount: number; responseRate: number | null };
};
export type ScoreSummary = {
  kind: "mean" | "positiveRate" | "unavailable"; value: number | null; positiveValue?: string;
};
export type QualityVersionSummary = {
  criteriaVersionId: number; criteriaVersion: number; validFrom: string; validTo: string | null;
  analysisCount: number; selectedJobCount: number; correctionRate: number | null;
  criteria: Array<{
    code: string; name: string; description: string; scale: Array<string | number>;
    scoredCount: number | null; missingCount: number | null; correctedCount: number | null;
    originalSummary: ScoreSummary; effectiveSummary: ScoreSummary;
  }>;
};
export type RatingFeedback = { state: "available" | "forbidden"; scaleSummaries: RatingScaleSummary[] };
export type QualityFeedback = { state: "available" | "forbidden"; versions: QualityVersionSummary[] };
