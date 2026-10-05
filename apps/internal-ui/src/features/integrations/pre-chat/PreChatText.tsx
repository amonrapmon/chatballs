import { fmt, t } from "../../../i18n";
import { Button } from "../../../shared/ui-controls";
import type { PreChatDraft } from "./model";

export function PreChatText({ draft, version, updatedAt, busy, error, onChange, onSave }: {
  draft: PreChatDraft;
  version: string;
  updatedAt: string;
  busy: boolean;
  error: string;
  onChange: (patch: Partial<PreChatDraft>) => void;
  onSave: () => void;
}) {
  const savedToday = new Date(updatedAt).toDateString() === new Date().toDateString();
  return <div className="portal-settings-card pre-chat-text">
    <label className="portal-field">
      <span className="portal-field-label">{t("pre_chat.title")}</span>
      <input value={draft.preChat.title} disabled={busy} onChange={(event) => onChange({ preChat: { ...draft.preChat, title: event.target.value } })} />
    </label>
    <label className="portal-field">
      <span className="portal-field-label">{t("pre_chat.consent")}</span>
      <textarea value={draft.consentText} disabled={busy} onChange={(event) => onChange({ consentText: event.target.value })} />
      <small>{t("pre_chat.consent_revision", { version: version.replace(/^v(?=\d)/, "") || "1" })}</small>
    </label>
    {error && <div className="integration-form-error" role="alert">{error}</div>}
    <div className="portal-settings-actions">
      <Button variant="primary" disabled={busy} onClick={onSave}>{busy ? t("ai.saving") : t("common.save")}</Button>
      <span className="portal-settings-gap" />
      {updatedAt && <span className="portal-settings-note">{savedToday
        ? t("pre_chat.saved_today", { time: fmt.time(updatedAt) })
        : t("portals.saved_at_lower", { date: fmt.shortDateTime(updatedAt) })}</span>}
    </div>
  </div>;
}
