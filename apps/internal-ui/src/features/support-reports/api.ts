import { api, ApiError, resolveApiUrl } from "../../api/client";
import type { PagedPayload } from "../../shared/usePagedResource";
import { loadOrganizationSettings } from "../administration/api";
import type { AgentCard } from "../agents/model";
import type { Employee } from "../../types";
import type { ApiConversation, WindowPage } from "../conversations/apiTypes";
import { dayPeriods, periodQuery } from "./period";
import type { DayReport, ReportDirectory, ReportFilters, ReportPeriod, SupportReport } from "./types";

const BASE = "/api/v1/conversations/support-report";
export const fetchReport = (period: ReportPeriod, signal: AbortSignal) => api<SupportReport>(`${BASE}/?${periodQuery(period)}`, { signal });

async function allPages<T>(path: string, signal: AbortSignal): Promise<T[]> {
  const items: T[] = [];
  for (let page = 1; ; page += 1) {
    const response = await api<PagedPayload<T>>(`${path}?page=${page}`, { signal });
    items.push(...response.items);
    if (page >= response.pageCount) return items;
  }
}

export async function fetchReportDirectory(signal: AbortSignal): Promise<ReportDirectory> {
  const [settings, employees, agents] = await Promise.all([
    loadOrganizationSettings(), allPages<Employee>("/api/v1/employees/", signal), allPages<AgentCard>("/api/v1/agents/", signal),
  ]);
  return { employees, connections: agents.flatMap((agent) => agent.connections), timezone: settings.organization.timezone, timezones: settings.timezones };
}

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

/** Current reply expectation comes from the live inbox, not historical intervals.
 * Both ordinary and archived records belong to the report's manager scope. */
export async function fetchWaitingReplies(period: ReportPeriod, signal: AbortSignal): Promise<Record<number, number>> {
  const counts: Record<number, number> = {};
  for (const archived of [false, true]) {
    let cursor: number | null = null;
    do {
      const params = new URLSearchParams({ lifecycle: "OPEN", limit: "100" });
      if (archived) params.set("archived", "1");
      if (cursor !== null) params.set("cursor", String(cursor));
      if (period.group !== null) params.set("group", String(period.group));
      if (period.employee !== null) params.set("assigned", String(period.employee));
      const response = await api<WindowPage<ApiConversation>>(`/api/v1/conversations/?${params}`, { signal });
      for (const item of response.items) {
        if (item.assignedOperatorId === null || item.expectedResponder !== "OPERATOR") continue;
        if (period.transport && item.connection?.provider !== period.transport) continue;
        if (period.connection !== null && item.connection?.id !== period.connection) continue;
        counts[item.assignedOperatorId] = (counts[item.assignedOperatorId] ?? 0) + 1;
      }
      cursor = response.hasMore ? response.cursor : null;
    } while (cursor !== null);
  }
  return counts;
}

export async function downloadReport(period: ReportPeriod, format: "csv" | "xlsx", signal: AbortSignal): Promise<Blob> {
  const response = await fetch(resolveApiUrl(`${BASE}.${format}?${periodQuery(period)}`), { credentials: "include", signal });
  if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => ({})));
  return response.blob();
}
