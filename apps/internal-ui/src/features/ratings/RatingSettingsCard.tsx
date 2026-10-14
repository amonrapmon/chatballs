import { Switch } from "antd";
import { Button } from "../../shared/ui-controls";
import { LoadingState } from "../../shared/ui";
import { fmt, t } from "../../i18n";
import { useRatingSettings } from "./useRatingSettings";
import "./settings.css";

export function RatingSettingsCard() {
  const state = useRatingSettings();
  const { draft, saved } = state;
  if (!draft || !saved) return state.error ? <p role="alert">{state.error}</p> : <LoadingState />;
  const missing = draft.scale.find(choice => !choice.label.trim());
  return <section className="rating-settings-card">
    <header><div><h3>{t("ratings.request_title")}</h3><p>{t("ratings.request_lead")}</p></div>
      <label className="rating-settings-toggle"><span>{t(draft.enabled ? "ratings.enabled" : "ratings.disabled")}</span>
        <Switch checked={draft.enabled} disabled={state.busy} onChange={enabled => state.setDraft({ ...draft, enabled })} aria-label={t("ratings.request_title")} /></label>
    </header>
    <fieldset disabled={state.busy || !draft.enabled} className={!draft.enabled ? "is-off" : ""}>
      <div className="rating-settings-labels"><span>{t("ratings.labels")}</span><div>
        {draft.scale.map((choice, index) => <label key={choice.value}><b>{fmt.number(choice.value)}</b>
          <input aria-label={`${t("ratings.labels")} ${fmt.number(choice.value)}`} maxLength={120} value={choice.label}
            placeholder={t("ratings.label_missing")} aria-invalid={state.invalidScale && !choice.label.trim()}
            onChange={event => state.setDraft({ ...draft, scale: draft.scale.map((item, i) => i === index ? { ...item, label: event.target.value } : item) })} /></label>)}
      </div>{state.invalidScale && <small className="rating-settings-error" role="alert">{t("ratings.labels_required")}</small>}<small>{t("ratings.labels_help")}</small></div>
      <label>{t("ratings.text")}<textarea rows={3} maxLength={4000} value={draft.text} onChange={event => state.setDraft({ ...draft, text: event.target.value })} /></label>
      <label className="rating-settings-delay">{t("ratings.delay")}<span><input aria-label={t("ratings.delay")} type="number" min={0} max={10080} step="any" value={state.minutes} onChange={event => state.setMinutes(event.target.value)} /><span>{t("ratings.delay_unit")}</span></span><small>{t("ratings.delay_help")}</small></label>
    </fieldset>
    <footer><small className={state.error || state.invalidScale ? "rating-settings-error" : ""} role={state.error ? "alert" : undefined}>
      {state.error || (state.invalidScale && missing ? t("ratings.unsaved_label", { value: fmt.number(missing.value) }) : saved.updatedAt ? t("settings.queue_saved_by", { when: fmt.shortDateTime(saved.updatedAt), who: saved.updatedBy }) : "")}
    </small><Button variant="primary" disabled={state.busy} onClick={() => void state.save()}>{t("common.save")}</Button></footer>
  </section>;
}
