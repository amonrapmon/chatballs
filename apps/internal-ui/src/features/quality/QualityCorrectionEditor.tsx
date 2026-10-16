import { Select } from "antd";
import { t } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import { valueLabel } from "./presentation";
import type { QualityCriterion } from "./types";
import type { useQualityCorrection } from "./useQualityCorrection";

export function QualityCorrectionEditor({ criterion, state }: { criterion: QualityCriterion; state: ReturnType<typeof useQualityCorrection> }) {
  return <>
    <div className="quality-correction-editor">
      <label><span>{t("quality.new_value")}</span><Select aria-label={t("quality.new_value")} disabled={state.busy || Boolean(state.conflict)} value={state.value}
        options={criterion.scale.map((value, index) => ({ value: index, label: valueLabel(value) }))} onChange={index => state.setValue(index)} /></label>
      <label><span>{t("quality.reason")}</span><textarea aria-label={t("quality.reason")} rows={2} disabled={state.busy} value={state.reason} aria-invalid={state.required && !state.reason.trim()} onChange={event => state.setReason(event.target.value)} />
        {state.required && !state.reason.trim() && <small role="alert" className="quality-error">{t("quality.reason_required")}</small>}</label>
      <div className="quality-editor-footer"><small>{state.error || t("quality.original_kept")}</small><Button variant="secondary" disabled={state.busy} onClick={state.cancel}>{t("common.cancel")}</Button>
        <Button variant="primary" disabled={state.busy || Boolean(state.conflict)} onClick={() => void state.save()}>{t("quality.save_value")}</Button></div>
    </div>
  </>;
}
