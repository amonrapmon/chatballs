import { t } from "../../i18n";
import type { EmployeeGroupRef } from "../../types";
import { calendarDate } from "./period";
import { dateLabel, periodLabel, timeLabel } from "./presentation";
import type { ReportDirectory, ReportFilters } from "./types";

export function ReportExportParameters({ filters, directory, groups, generatedAt }: {
  filters: ReportFilters; directory: ReportDirectory; groups: EmployeeGroupRef[]; generatedAt: string;
}) {
  const all = t("reports.all");
  const today = calendarDate(new Date(generatedAt), filters.timezone);
  const period = periodLabel(filters);
  const transport = (["web", "email", "telegram", "max", "vk"] as const).find((key) => key.toUpperCase() === filters.transport);
  const employee = directory.employees.find((item) => String(item.id) === filters.employee);
  const rows = [
    [t("reports.period"), filters.start <= today && today <= filters.end
      ? t("reports.period_current", { period, date: dateLabel(today, filters.timezone), time: timeLabel(generatedAt, filters.timezone) }) : period],
    [t("reports.timezone"), filters.timezone],
    [t("reports.employee"), employee?.fullName || employee?.email || all],
    [t("reports.group"), groups.find((item) => String(item.id) === filters.group)?.name || (directory.restricted ? groups.map(row => row.name).join(", ") : all)],
    [t("reports.transport"), transport ? t(`reports.channel_${transport}`) : all],
    [t("reports.connection"), directory.connections.find((item) => String(item.id) === filters.connection)?.name || all],
  ];
  return <div className="report-export-parameters">{rows.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>;
}
