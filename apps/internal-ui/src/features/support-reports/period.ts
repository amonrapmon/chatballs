import type { ReportFilters, ReportPeriod } from "./types";

/** Calendar arithmetic is deliberately separate from elapsed milliseconds. */
export function addDays(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function calendarDate(value: Date, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(value);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** Resolve local midnight with the offset on that date, including DST changes. */
export function midnight(value: string, timezone: string): string {
  const target = Date.parse(`${value}T00:00:00Z`);
  if (!Number.isFinite(target)) throw new RangeError("Invalid calendar date");
  const format = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
  let instant = target;
  for (let i = 0; i < 4; i += 1) {
    const parts = format.formatToParts(new Date(instant));
    const get = (type: string) => Number(parts.find((part) => part.type === type)?.value);
    const wall = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
    if (wall === target) return new Date(instant).toISOString();
    instant += target - wall;
  }
  // A few zones skip midnight; the first existing moment of the calendar day
  // is its boundary. Find it by date rather than inventing a fixed UTC offset.
  let left = target - 36 * 3_600_000;
  let right = target + 36 * 3_600_000;
  while (right - left > 1) {
    const middle = Math.floor((left + right) / 2);
    if (calendarDate(new Date(middle), timezone) < value) left = middle;
    else right = middle;
  }
  if (calendarDate(new Date(right), timezone) !== value) throw new RangeError("Calendar date does not exist in this timezone");
  return new Date(right).toISOString();
}

export function initialFilters(timezone: string, now = new Date()): ReportFilters {
  const end = calendarDate(now, timezone);
  return { start: addDays(end, -6), end, timezone, employee: "", group: "", transport: "", connection: "" };
}

export function reportPeriod(filters: ReportFilters): ReportPeriod {
  if (filters.start > filters.end) throw new RangeError("Reversed report period");
  return {
    from: midnight(filters.start, filters.timezone), to: midnight(addDays(filters.end, 1), filters.timezone),
    timezone: filters.timezone,
    employee: filters.employee ? Number(filters.employee) : null,
    group: filters.group ? Number(filters.group) : null,
    connection: filters.connection ? Number(filters.connection) : null,
    transport: filters.transport || null,
  };
}

export function dayPeriods(filters: ReportFilters): Array<{ date: string; period: ReportPeriod }> {
  const result = [];
  for (let date = filters.start; date <= filters.end; date = addDays(date, 1)) {
    result.push({ date, period: reportPeriod({ ...filters, start: date, end: date }) });
  }
  return result;
}

export function periodQuery(period: ReportPeriod): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(period)) if (value !== null) params.set(key, String(value));
  return params.toString();
}
