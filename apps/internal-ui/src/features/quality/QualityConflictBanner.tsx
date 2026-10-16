import { fmt, t } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import { QualityBanner } from "./QualityBanner";
import { criterionName, valueLabel } from "./presentation";
import type { QualityJob } from "./types";

export type QualityConflict = { key: string; job: QualityJob; showCurrent: () => void; cancel: () => void };
export type ReportQualityConflict = (view: QualityConflict | null, key: string) => void;

export function QualityConflictBanner({ conflict }: { conflict: QualityConflict }) {
  const latest = conflict.job.corrections.at(-1);
  if (!latest) return null;
  const criterion = conflict.job.criteria.find(row => row.code === latest.criterionCode);
  const previous = conflict.job.corrections.filter(row => row.criterionCode === latest.criterionCode).at(-2)?.value
    ?? conflict.job.conclusions.find(row => row.code === latest.criterionCode)?.originalValue;
  return <QualityBanner tone="warning" title={t("quality.conflict_title", { criterion: criterion ? criterionName(criterion) : "", author: latest.author?.name || t("common.operator") })}
    text={t("quality.conflict_note", { value: valueLabel(latest.value), previous: previous === undefined ? "—" : valueLabel(previous), time: fmt.time(latest.createdAt) })}
    actions={<><Button variant="secondary" onClick={conflict.showCurrent}>{t("quality.show_current")}</Button><Button variant="secondary" onClick={conflict.cancel}>{t("quality.cancel_correction")}</Button></>} />;
}
