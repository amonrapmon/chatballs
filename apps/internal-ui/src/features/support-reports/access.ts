import type { ReportDirectory, ReportFilters } from "./types";

/** Changing any allowed identity invalidates loaded results and export snapshots. */
export function reportScopeKey(directory: ReportDirectory | null): string {
  if (!directory) return "";
  return JSON.stringify([directory.actions, directory.restricted,
    directory.groups.map(row => row.id), directory.employees.map(row => row.id),
    directory.connections.map(row => row.id)]);
}

export function allowedFilters(filters: ReportFilters, directory: ReportDirectory): ReportFilters {
  const allowed = (value: string, rows: Array<{ id: number }>) => !value || rows.some(row => String(row.id) === value);
  const next = { ...filters,
    group: allowed(filters.group, directory.groups) ? filters.group : "",
    employee: allowed(filters.employee, directory.employees) ? filters.employee : "",
    connection: allowed(filters.connection, directory.connections) ? filters.connection : "",
  };
  return Object.keys(next).every(key => next[key as keyof ReportFilters] === filters[key as keyof ReportFilters]) ? filters : next;
}
