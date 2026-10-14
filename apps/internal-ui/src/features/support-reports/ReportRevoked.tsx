import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import { timeLabel } from "./presentation";

export function ReportRevoked({ occurredAt, timezone, onDialogs }: { occurredAt: string; timezone: string; onDialogs: () => void }) {
  return <div className="report-state" role="status">
    <span className="report-state-icon"><Icon name="lock" size={20} /></span>
    <h3>{t("reports.revoked_title")}</h3>
    <p>{t("reports.revoked_text", { time: timeLabel(occurredAt, timezone) })}</p>
    <Button variant="secondary" onClick={onDialogs}>{t("reports.to_dialogs")}</Button>
  </div>;
}
