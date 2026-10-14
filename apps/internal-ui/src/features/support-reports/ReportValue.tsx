import { fmt, t } from "../../i18n";
import { durationLabel, missing } from "./presentation";

export function ReportValue({ value, duration = false, title }: { value: number | null; duration?: boolean; title?: string }) {
  return <span className={value === null ? "report-value is-missing" : "report-value"} title={title ?? (value === null ? t("reports.no_value") : undefined)}>
    {duration ? durationLabel(value) : value === null ? missing : fmt.number(value)}
  </span>;
}
