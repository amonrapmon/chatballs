import type { Employee, EmployeeGroupRef } from "../../types";
import type { WorkStatusCode } from "../work-status/model";
import type { QualityFeedback, RatingFeedback } from "./feedbackTypes";

export type ReportFilters = {
  start: string;
  end: string;
  timezone: string;
  employee: string;
  group: string;
  transport: string;
  connection: string;
};
export type ReportPeriod = {
  from: string; to: string; timezone: string;
  employee: number | null; group: number | null;
  transport: string | null; connection: number | null;
};
export const countKeys = ["accepted", "completed", "transferred", "receivedTransfers", "humanReplies", "aiReplies"] as const;
export type CountKey = typeof countKeys[number];
export const durationKeys = ["waiting", "handling", "firstResponse", "subsequentResponse", "aiResponse"] as const;
export type DurationKey = typeof durationKeys[number];
export type Duration = { seconds: number | null; observedSeconds: number; samples: number; currentIntervals: number; meanSeconds?: number | null };
export type Metrics = {
  complete: boolean;
  completeByMetric?: Record<CountKey | DurationKey, boolean>;
  observedCounts: Record<CountKey, number>;
  values: Record<CountKey, number | null> & Record<DurationKey, Duration>;
};
export type StatusDuration = { seconds: number | null; observedSeconds: number; currentIntervals: number };
export type WorkStatuses = {
  complete: boolean; included: boolean; availableFrom: string | null;
  values: Record<WorkStatusCode, StatusDuration>;
};
export type ReportEmployee = {
  employee: number; name: string; blocked: boolean; active: boolean;
  currentLoad: number; metrics: Metrics; workStatuses: WorkStatuses;
  waitingReplies: number;
  customerRatings: RatingFeedback; qualityAnalysis: QualityFeedback;
};
export type SupportReport = {
  period: ReportPeriod; generatedAt: string; durationUnit: "seconds";
  currentLoad: number; totals: Metrics; employees: ReportEmployee[];
  customerRatings: RatingFeedback; qualityAnalysis: QualityFeedback;
  coverage: { availableFrom: string | null; complete: boolean; incompleteConversationIds: number[]; reason: string | null };
  workStatusDetails: Array<{ employee: number; status: WorkStatusCode; from: string; to: string; seconds: number; current: boolean }>;
};
export type DayReport = { date: string; report: SupportReport };
export type ReportDirectory = {
  actions: string[];
  restricted: boolean;
  revokedAt: string | null;
  groups: EmployeeGroupRef[];
  employees: ReportStaff[];
  connections: Array<{ id: number; name: string; provider: string }>;
  timezone: string;
  timezones: string[];
};
export type ReportStaff = Pick<Employee, "id" | "fullName" | "email" | "avatarUrl" | "isBlocked" | "workStatus" | "online" | "lastSeenAt">;
export type ReportTab = "conversations" | "workload" | "ratings" | "quality";
