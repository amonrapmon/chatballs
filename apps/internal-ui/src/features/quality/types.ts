import type { Metrics } from "../support-reports/types";

export type QualityValue = string | number;
export type QualityCriterion = { code: string; name?: string; description: string; scale: QualityValue[]; reporting?: { positiveValue: string } };
export type QualityScale = { id: string; label: string; values: QualityValue[] };
export type QualitySettings = {
  enabled: boolean; criteriaVersion: number | null; nextCriteriaVersion: number; criteriaCreatedAt: string | null;
  criteria: QualityCriterion[]; scales: QualityScale[];
  suggestedCriteria?: QualityCriterion[] | null;
  criteriaValueLiterals: Record<string, string[]>;
};
export type QualityCorrection = {
  revision: number; criterionCode: string; value: QualityValue; reason: string; createdAt: string;
  author: { membershipId: number; userId: number; name: string } | null;
};
export type QualityConclusion = {
  code: string; originalValue: QualityValue | null; effectiveValue: QualityValue | null; explanation: string;
  effectiveScaleIndex: number | null; missingReason?: "insufficient_messages" | null;
  recommendations: string[]; evidence: { messageId: number; url: string }[]; evidenceAvailable: boolean;
};
export type QualityJob = {
  id: number; conversationId: number; criteriaVersion: number; criteria: QualityCriterion[];
  revision: number; historyRevision: string; completionEventId: string; completedAt: string;
  state: "WAITING" | "RUNNING" | "SUCCEEDED" | "FAILED"; errorCode: string | null;
  startedAt: string | null; finishedAt: string | null; resultId: number | null;
  conclusions: QualityConclusion[]; correctionRevision: number; corrections: QualityCorrection[];
  temporalFacts: { state: "available" | "missing_history"; availableFrom: string | null; metrics: Metrics };
};
export type QualityEvidence = { messageId: number; conversationId: number; authorType: string; createdAt: string; text: string; contentHtml: string; transcript: string };
