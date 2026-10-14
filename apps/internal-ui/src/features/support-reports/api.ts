import { api, ApiError, resolveApiUrl } from "../../api/client";
import { dayPeriods, periodQuery } from "./period";
import type { DayReport, ReportDirectory, ReportFilters, ReportPeriod, SupportReport } from "./types";

const BASE = "/api/v1/conversations/support-report";
export const fetchReport = (period: ReportPeriod, signal: AbortSignal) => api<SupportReport>(`${BASE}/?${periodQuery(period)}`, { signal });

export const fetchReportDirectory = (signal: AbortSignal) => api<ReportDirectory>(`${BASE}/access/`, { signal });

/** Bounded parallelism keeps arbitrary date ranges from flooding the backend. */
export async function fetchDayReports(filters: ReportFilters, signal: AbortSignal): Promise<DayReport[]> {
  const periods = dayPeriods(filters);
  const result: DayReport[] = [];
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(3, periods.length) }, async () => {
    while (next < periods.length) {
      signal.throwIfAborted();
      const index = next++;
      const day = periods[index];
      result[index] = { date: day.date, report: await fetchReport(day.period, signal) };
    }
  }));
  return result;
}

export async function downloadReport(period: ReportPeriod, format: "csv" | "xlsx", signal: AbortSignal): Promise<Blob> {
  const response = await fetch(resolveApiUrl(`${BASE}.${format}?${periodQuery(period)}`), { credentials: "include", signal });
  if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => ({})));
  return response.blob();
}
