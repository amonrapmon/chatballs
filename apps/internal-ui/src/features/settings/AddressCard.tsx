import { useState, type FormEvent } from "react";

import { t } from "../../i18n";
import { FormField } from "../../shared/form-controls";
import { Button } from "../../shared/ui-controls";
import { instanceError, patchInstance, type InstancePayload } from "./instance";
import { savedLabel } from "./platformSettingsModel";

export function AddressCard({ canManage, current, onSaved }: {
  canManage: boolean;
  current: InstancePayload;
  onSaved: (payload: InstancePayload) => void;
}) {
  const [host, setHost] = useState(current.publicHost);
  const [scheme, setScheme] = useState<"http" | "https">(current.publicScheme);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [errorText, setErrorText] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const touch = () => { setFieldErrors({}); setMessage(""); setErrorText(""); };

  async function save() {
    setBusy(true);
    setMessage("");
    setErrorText("");
    setFieldErrors({});
    try {
      const payload = await patchInstance({ publicHost: host, publicScheme: scheme });
      onSaved(payload);
      setHost(payload.publicHost);
      setScheme(payload.publicScheme);
      setMessage(t("settings.saved_file_links_will_use"));
    } catch (error) {
      const { detail, errors } = instanceError(error);
      setErrorText(detail);
      setFieldErrors(errors);
    } finally {
      setBusy(false);
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
          <strong>{t("settings.installation_address")}</strong>
          <small>{t("settings.system_opened_at_file_links")}</small>
        </div>
        <div className="appearance-theme-options">
          {(["http", "https"] as const).map((value) => (
            <button
              className={scheme === value ? "active" : ""}
              disabled={!canManage || busy}
              key={value}
              type="button"
              onClick={() => { setScheme(value); touch(); }}
            >
              {value}
            </button>
          ))}
        </div>
      </div>
      <p className="settings-section-note">
        {t("settings.address_hint")} <b>{scheme}://{host || t("settings.address_placeholder")}/…</b>
      </p>
      <div className="administration-fields">
        <FormField
          disabled={!canManage}
          error={fieldErrors.publicHost}
          label={t("settings.domain_or_ip")}
          mono
          placeholder="crm.example.com"
          value={host}
          wide
          onChange={(value) => { setHost(value); touch(); }}
        />
      </div>
      {errorText && <div className="administration-message error" role="alert">{errorText}</div>}
      {canManage && (
        <div className="administration-actions">
          <small className="administration-saved">{message || savedLabel(current.updatedAt)}</small>
          <Button type="submit" variant="primary" disabled={busy || !host.trim()}>
            {busy ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      )}
    </form>
  );
}
