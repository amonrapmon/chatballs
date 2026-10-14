import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import { hasFilters, periodLabel } from "./presentation";
import type { ReportFilters } from "./types";

export function ReportState({ error, errorMessage, filters, group, connection, retry, reset, selectPeriod }: { error: boolean; errorMessage?: string; filters: ReportFilters | null; group?: string; connection?: string; retry: () => void; reset: () => void; selectPeriod: () => void }) {
  const filtered = filters && hasFilters(filters);
  const filteredText = filters && group && connection
    ? t("reports.filtered_detail", { group, connection, period: periodLabel(filters) }) : t("reports.filtered_text");
  return <div className={`report-state${error ? " is-error" : ""}`} role={error ? "alert" : undefined}>
    <span className="report-state-icon"><Icon name={error ? "errorCircle" : "info"} size={20} /></span>
    <h3>{error ? t("reports.error_title") : filtered ? t("reports.filtered_title") : t("reports.empty_title", { period: filters ? periodLabel(filters) : "" })}</h3>
    <p>{error ? errorMessage ?? t("reports.error_text") : filtered ? filteredText : t("reports.empty_text")}</p>
    <Button variant="secondary" onClick={error ? retry : filtered ? reset : selectPeriod}>{error ? t("reports.retry") : filtered ? t("reports.reset_filters") : t("reports.select_period")}</Button>
  </div>;
}
