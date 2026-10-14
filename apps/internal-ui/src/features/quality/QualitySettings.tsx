import { useEffect, useState } from "react";
import { Switch } from "antd";
import { fmt, t } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import { QualityCriterionRow } from "./QualityCriterionRow";
import { useQualitySettings } from "./useQualitySettings";
import type { QualityCriterion } from "./types";
import "./settings.css";

export function QualitySettings() {
  const state = useQualitySettings();
  const [editing, setEditing] = useState<string | null>(null);
  const [beforeEdit, setBeforeEdit] = useState<QualityCriterion | null>(null);
  const [newName, setNewName] = useState("");
  const { saved, draft } = state;
  useEffect(() => { setEditing(null); setBeforeEdit(null); }, [saved?.criteriaVersion]);
  if (!saved) return state.error ? <p role="alert">{state.error}</p> : null;
  const criteria = draft || saved.criteria;
  function update(next: QualityCriterion[]) { state.setDraft(next); }
  function add() {
    if (!newName.trim()) return;
    const code = `criterion_${crypto.randomUUID().replaceAll("-", "")}`;
    update([...criteria, { code, name: newName.trim(), description: "", scale: [] }]);
    setEditing(code); setBeforeEdit(null); setNewName("");
  }
  return <div className="quality-settings">
    <section className="quality-settings-card"><header><div><h3>{t("quality.enable_title")}</h3><p>{t("quality.enable_lead")}</p></div>
      <label className="quality-settings-toggle"><span>{t(saved.enabled ? "ratings.enabled" : "ratings.disabled")}</span><Switch checked={saved.enabled} disabled={state.busy} aria-label={t("quality.enable_title")} onChange={enabled => void state.save(enabled)} /></label>
    </header></section>
    <section className="quality-settings-card"><header><h3>{t("quality.criteria")}</h3>
      {(saved.criteriaVersion !== null || draft) && <b className={`quality-chip ${draft ? "is-draft" : "is-version"}`}>{t(draft ? "quality.draft_version" : "quality.version_date", { version: fmt.number(draft ? saved.nextCriteriaVersion : saved.criteriaVersion || 0), date: saved.criteriaCreatedAt ? fmt.shortDate(saved.criteriaCreatedAt) : "" })}</b>}
    </header><p className="quality-criteria-lead">{t("quality.criteria_lead")}</p>
      <div className="quality-criteria-table"><div className="quality-criteria-row quality-criteria-head"><span>{t("quality.criterion")}</span><span>{t("quality.description")}</span><span>{t("quality.scale")}</span><span /></div>
        {criteria.map(item => <QualityCriterionRow key={item.code} item={item} scales={saved.scales} busy={state.busy} invalid={state.invalid} editing={editing === item.code}
          change={changed => update(criteria.map(row => row.code === item.code ? changed : row))} edit={() => { setBeforeEdit({ ...item, scale: [...item.scale] }); update(criteria.map(row => ({ ...row, name: row.name || row.description }))); setEditing(item.code); }}
          remove={() => { update(criteria.filter(row => row.code !== item.code)); setEditing(null); }}
          cancel={() => { update(beforeEdit ? criteria.map(row => row.code === item.code ? beforeEdit : row) : criteria.filter(row => row.code !== item.code)); setEditing(null); }}
          finish={() => { if (item.name?.trim() && item.description.trim() && item.scale.length) setEditing(null); else void state.save(saved.enabled, criteria); }} />)}
      </div>
      {!editing && <div className="quality-add-row"><input aria-label={t("quality.new_criterion")} placeholder={t("quality.new_criterion")} value={newName} disabled={state.busy} onChange={event => setNewName(event.target.value)} onKeyDown={event => { if (event.key === "Enter") add(); }} />
        <Button variant="secondary" icon="plus" disabled={state.busy || !newName.trim()} onClick={add}>{t("quality.create")}</Button></div>}
      {draft && <footer><small role={state.error || state.invalid ? "alert" : undefined}>{state.error || (state.invalid ? criteria.some(item => !item.scale.length) ? t("quality.unsaved_scale", { name: criteria.find(item => !item.scale.length)?.name || "" }) : t("common.request_failed") : saved.criteriaVersion === null ? t("quality.criteria_lead") : t("quality.new_version_note", { version: fmt.number(saved.nextCriteriaVersion), previous: fmt.number(saved.criteriaVersion || 0) }))}</small>
        <Button variant="secondary" disabled={state.busy} onClick={() => { state.setDraft(null); setEditing(null); }}>{t("quality.cancel_changes")}</Button>
        <Button variant="primary" disabled={state.busy} onClick={() => void state.save(saved.enabled, criteria)}>{t("quality.save_version", { version: fmt.number(saved.nextCriteriaVersion) })}</Button></footer>}
    </section>{state.error && !draft && <p role="alert" className="quality-error">{state.error}</p>}
  </div>;
}
