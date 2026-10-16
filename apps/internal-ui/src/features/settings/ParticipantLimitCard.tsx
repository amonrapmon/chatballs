import { Button } from "../../shared/ui-controls";
import { fmt, t, tn } from "../../i18n";
import { useParticipantLimit } from "./useParticipantLimit";
import "./participant-limit.css";

/** N1–N2: the participants card, independent of transfer reasons and status policy. */
export function ParticipantLimitCard({ canManage }: { canManage: boolean }) {
  const limit = useParticipantLimit();
  if (!limit.saved) return limit.error ? <p className="settings-section-error" role="alert">{limit.error}</p> : null;
  const updatedAt = limit.saved.updatedAt;
  const changed = limit.draft !== String(limit.saved.additionalParticipantLimit);
  return (
    <section className="participant-limit-card">
      <header>
        <h3>{t("participants.limit_title")}</h3>
        <p>{t("participants.limit_lead")}</p>
      </header>
      <div className="participant-limit-fields">
        <label htmlFor="participant-limit">{t("participants.limit_label")}</label>
        <div className={`participant-limit-input ${limit.fieldError ? "is-error" : ""}`}>
          <input id="participant-limit" type="number" min={1} max={10} step={1} value={limit.draft}
            disabled={limit.busy || !canManage} aria-invalid={Boolean(limit.fieldError)}
            aria-describedby="participant-limit-help participant-limit-error"
            onChange={(event) => limit.setDraft(event.target.value)} />
          <span>{tn("participants.limit_unit", Number(limit.draft) || 0)}</span>
        </div>
        <small id="participant-limit-error" className="participant-limit-error" role={limit.fieldError ? "alert" : undefined}>{limit.fieldError}</small>
        <small id="participant-limit-help">{t("participants.limit_help")}</small>
      </div>
      <footer>
        <small className={limit.fieldError || limit.error ? "participant-limit-error" : undefined}>
          {limit.error || (limit.fieldError ? t("participants.limit_invalid") : updatedAt
            ? t("settings.queue_saved_by", { when: fmt.shortDateTime(updatedAt), who: limit.saved.updatedBy }) : "")}
        </small>
        {canManage && <Button variant="primary" disabled={limit.busy || !changed} onClick={() => void limit.save()}>{t("common.save")}</Button>}
      </footer>
    </section>
  );
}
