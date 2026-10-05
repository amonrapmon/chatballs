import { useState, type FormEvent } from "react";

import { t } from "../../i18n";
import { FormField, SwitchButton } from "../../shared/form-controls";
import { Button } from "../../shared/ui-controls";
import { checkInstanceEmail, instanceError, patchInstance, type InstancePayload } from "./instance";
import { emailDraftOf, savedLabel, type EmailDraft } from "./platformSettingsModel";

export function EmailCard({ canManage, current, onSaved }: {
  canManage: boolean;
  current: InstancePayload;
  onSaved: (payload: InstancePayload) => void;
}) {
  const [draft, setDraft] = useState<EmailDraft>(() => emailDraftOf(current.email));
  const [busy, setBusy] = useState<"" | "save" | "check">("");
  const [message, setMessage] = useState("");
  const [errorText, setErrorText] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const touch = () => { setFieldErrors({}); setMessage(""); setErrorText(""); };
  const set = (key: keyof EmailDraft) => (value: string) => { setDraft({ ...draft, [key]: value }); touch(); };

  async function save() {
    setBusy("save");
    setMessage("");
    setErrorText("");
    setFieldErrors({});
    try {
      const payload = await patchInstance({
        email: {
          host: draft.host,
          port: Number(draft.port) || 587,
          user: draft.user,
          password: draft.password,
          useTls: draft.useTls,
          from: draft.from,
        },
      });
      onSaved(payload);
      setDraft(emailDraftOf(payload.email));
      setMessage(t("settings.saved_email_will_go_through"));
    } catch (error) {
      const { detail, errors } = instanceError(error);
      setErrorText(detail);
      setFieldErrors(errors);
    } finally {
      setBusy("");
    }
  }

  async function check() {
    setBusy("check");
    setMessage("");
    setErrorText("");
    try {
      const sent = await checkInstanceEmail();
      setMessage(t("settings.email_sent_to", { email: sent }));
    } catch (error) {
      setErrorText(instanceError(error).detail);
    } finally {
      setBusy("");
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void save();
  }

  return (
    <form className="administration-card" onSubmit={submit}>
      <div className="settings-card-head">
        <div>
          <strong>{t("settings.outgoing_email")}</strong>
          <small>{t("settings.operator_invitations_password_resets")}</small>
        </div>
        {/* Шифрование канала до SMTP — двоичный выбор, значит переключатель
            (тот же стандарт, что у точек входа в «Голосовых и звонках»). */}
        <div className="settings-card-head-switch">
          <span>TLS</span>
          <SwitchButton
            checked={draft.useTls}
            className="ui-switch is-compact"
            disabled={!canManage || Boolean(busy)}
            label={t("settings.tls_encryption_smtp_server")}
            onClick={() => { setDraft({ ...draft, useTls: !draft.useTls }); touch(); }}
          />
        </div>
      </div>
      {!current.email.configured && (
        <p className="settings-section-note">{t("settings.email_not_configured_nothing_sent")}</p>
      )}
      <div className="administration-fields">
        <FormField
          disabled={!canManage}
          error={fieldErrors.emailHost}
          label={t("settings.smtp_server")}
          mono
          placeholder="smtp.example.com"
          value={draft.host}
          onChange={set("host")}
        />
        <FormField
          disabled={!canManage}
          error={fieldErrors.emailPort}
          label={t("settings.port")}
          mono
          placeholder="587"
          value={draft.port}
          onChange={set("port")}
        />
        <FormField
          disabled={!canManage}
          label={t("settings.user")}
          mono
          placeholder="robot@example.com"
          value={draft.user}
          onChange={set("user")}
        />
        <FormField
          disabled={!canManage}
          label={t("common.password")}
          mono
          placeholder={current.email.hasPassword ? t("settings.saved") : ""}
          type="password"
          value={draft.password}
          onChange={set("password")}
        />
        <FormField
          disabled={!canManage}
          label={t("settings.sender")}
          placeholder="Chatballs <no-reply@example.com>"
          value={draft.from}
          wide
          onChange={set("from")}
        />
      </div>
      {errorText && <div className="administration-message error" role="alert">{errorText}</div>}
      {message && <div className="administration-message">{message}</div>}
      {canManage && (
        <div className="administration-actions">
          <small className="administration-saved">{savedLabel(current.updatedAt)}</small>
          {current.email.configured && (
            <Button variant="secondary" disabled={Boolean(busy)} onClick={() => void check()}>
              {busy === "check" ? t("settings.sending") : t("settings.send_test_email")}
            </Button>
          )}
          <Button type="submit" variant="primary" disabled={Boolean(busy)}>
            {busy === "save" ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      )}
    </form>
  );
}
