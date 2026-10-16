import { api } from "../../api/client";
import type { QualityCriterion, QualityEvidence, QualityJob, QualitySettings } from "./types";
import { serializeCriteria } from "./serialization";

const base = "/api/v1/conversations/";
export const fetchQualitySettings = () => api<QualitySettings>(`${base}quality/settings/`);
export const saveQualitySettings = (enabled: boolean, saved: QualitySettings, criteria?: QualityCriterion[]) => api<QualitySettings>(`${base}quality/settings/`, {
  method: "PUT", body: `{"enabled":${JSON.stringify(enabled)}${criteria ? `,"criteria":${serializeCriteria(criteria, saved)}` : ""}}`,
});
export const fetchQualityJobs = (id: number) => api<{ jobs: QualityJob[] }>(`${base}${id}/quality/`);
export const fetchQualityJob = (id: number) => api<QualityJob>(`${base}quality/jobs/${id}/`);
export const launchQuality = (id: number, operationId: string, repeat: boolean) => api<QualityJob>(`${base}${id}/quality/launch/`, {
  method: "POST", body: JSON.stringify({ operationId, repeat }),
});
export const correctQuality = (id: number, expectedRevision: number, criterionCode: string, scaleIndex: number, reason: string) =>
  api<QualityJob>(`${base}quality/jobs/${id}/corrections/`, { method: "POST", body: JSON.stringify({ expectedRevision, criterionCode, scaleIndex, reason }) });
export const fetchQualityEvidence = (url: string) => api<QualityEvidence>(url);
