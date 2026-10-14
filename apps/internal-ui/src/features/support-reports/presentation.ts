import { fmt, t } from "../../i18n";
import type { DurationKey, Metrics, ReportFilters, SupportReport } from "./types";

export function dateLabel(date: string, _timezone: string, year = false): string {
  // A calendar date must not shift into another day in distant timezones.
  return new Intl.DateTimeFormat(fmt.tag(), { timeZone: "UTC", day: "numeric", month: "short", ...(year ? { year: "numeric" } : {}) }).format(new Date(`${date}T12:00:00Z`));
}
export function instantLabel(instant: string, timezone: string): string {
  return new Intl.DateTimeFormat(fmt.tag(), { timeZone: timezone, day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(instant));
}
export function timeLabel(instant: string, timezone: string): string {
  return new Intl.DateTimeFormat(fmt.tag(), { timeZone: timezone, hour: "2-digit", minute: "2-digit" }).format(new Date(instant));
}
export const missing = "—";
export function durationLabel(seconds: number | null): string {
  if (seconds === null) return missing;
  const rounded = Math.round(seconds * 100) / 100;
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const rest = Math.round((rounded % 60) * 100) / 100;
  return [hours ? `${fmt.number(hours)} ${t("reports.hours")}` : "", minutes ? `${fmt.number(minutes)} ${t("reports.minutes")}` : "",
    rest || (!hours && !minutes) ? `${fmt.number(rest)} ${t("reports.seconds")}` : ""].filter(Boolean).join(" ");
}
export function metricDuration(metrics: Metrics, key: DurationKey): number | null {
  const value = metrics.values[key];
  return key.endsWith("Response") ? value.meanSeconds ?? null : value.seconds;
}
export function periodLabel(filters: ReportFilters): string {
  const formatter = new Intl.DateTimeFormat(fmt.tag(), { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" });
  return formatter.formatRange(new Date(`${filters.start}T12:00:00Z`), new Date(`${filters.end}T12:00:00Z`));
}
export function hasFilters(filters: ReportFilters): boolean {
  return Boolean(filters.employee || filters.group || filters.transport || filters.connection);
}
export function emptyPeriod(report: SupportReport): boolean {
  // Unobserved history is unknown, never an empty result with fabricated zeros.
  return report.coverage.complete && Object.values(report.totals.observedCounts).every((value) => value === 0)
    && Object.values(report.totals.values).every((value) => typeof value !== "object" || value === null || value.samples === 0);
}
export function coverageTitle(report: SupportReport): string {
  return report.coverage.availableFrom
    ? t("reports.available_since", { date: instantLabel(report.coverage.availableFrom, report.period.timezone) })
    : t("reports.no_value");
}
