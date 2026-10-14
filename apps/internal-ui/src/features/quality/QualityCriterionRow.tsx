import { Select } from "antd";
import { t } from "../../i18n";
import { IconButton } from "../../shared/ui-controls";
import { criterionName, sameScale, scaleLabel } from "./presentation";
import type { QualityCriterion, QualityScale } from "./types";

export function QualityCriterionRow({ item, scales, editing, busy, invalid, change, edit, remove, cancel, finish }: {
  item: QualityCriterion; scales: QualityScale[]; editing: boolean; busy: boolean; invalid: boolean;
  change: (item: QualityCriterion) => void; edit: () => void; remove: () => void; cancel: () => void; finish: () => void;
}) {
  const selected = scales.find(scale => sameScale(scale.values, item.scale));
  return <div className={`quality-criteria-row ${editing ? "is-editing" : ""}`}>
    {editing ? <><input aria-label={t("quality.criterion")} aria-invalid={invalid && !item.name?.trim()} maxLength={200} value={item.name || ""} disabled={busy} onChange={event => change({ ...item, name: event.target.value })} />
      <input aria-label={t("quality.description")} aria-invalid={invalid && !item.description.trim()} value={item.description} disabled={busy} onChange={event => change({ ...item, description: event.target.value })} />
      <div><Select aria-label={t("quality.scale")} value={selected?.id || (item.scale.length ? "existing" : undefined)} disabled={busy} status={invalid && !item.scale.length ? "error" : undefined}
        placeholder={t("quality.choose_scale")} options={[...scales.map(scale => ({ value: scale.id, label: scale.label })), ...(!selected && item.scale.length ? [{ value: "existing", label: scaleLabel(item.scale) }] : [])]}
        onChange={id => { const scale = scales.find(choice => choice.id === id); if (scale) change({ ...item, scale: [...scale.values] }); }} />
        {invalid && !item.scale.length && <small role="alert">{t("quality.choose_scale")}</small>}</div>
      <span className="quality-row-actions"><IconButton bare icon="check" label={t("quality.finish")} disabled={busy} onClick={finish} /><IconButton bare icon="close" label={t("common.cancel")} disabled={busy} onClick={cancel} /></span></>
      : <><strong>{criterionName(item)}</strong><span>{item.description}</span><span><b className="quality-chip">{scaleLabel(item.scale)}</b></span>
        <span className="quality-row-actions"><IconButton bare icon="edit" label={t("common.edit")} disabled={busy} onClick={edit} /><IconButton bare icon="trash" label={t("quality.remove")} disabled={busy} onClick={remove} /></span></>}
  </div>;
}
