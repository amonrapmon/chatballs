import { useEffect, useState } from "react";

import { DecisionDialog } from "../../shared/DecisionDialog";
import { SwitchButton } from "../../shared/form-controls";
import { Icon } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import { startedLabel } from "../conversations/DialogControls";
import { instanceError, loadToolsNetwork, patchToolsNetwork, type ToolsNetworkPayload } from "./instance";
import { t } from "../../i18n";

// «Локальная сеть» (кадры A3–A5): инструменты агентов всех организаций
// получают доступ к частным адресам сети, где стоит установка. Включение — только
// через окно с предупреждением; выключение безопасно и идёт сразу. Кто и когда
// включил, помнит сервер и показывает строка под карточкой.

function savedLabel(current: ToolsNetworkPayload): string {
  if (!current.enabled || !current.enabledAt) return t("settings.tools_network_unchanged");
  const when = startedLabel(current.enabledAt);
  // Включившего могли удалить — тогда остаётся только время.
  if (!current.enabledBy) return t("settings.tools_network_enabled_at", { when });
  return t("settings.tools_network_enabled_by", { name: current.enabledBy.name, when });
}

export function ToolsNetworkCard({ organizationName }: { organizationName: string }) {
  const [current, setCurrent] = useState<ToolsNetworkPayload | null>(null);
  const [loadError, setLoadError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [errorText, setErrorText] = useState("");

  useEffect(() => {
    loadToolsNetwork()
      .then(setCurrent)
      .catch(() => setLoadError(t("settings.could_not_load_installation_settings")));
  }, []);

  if (loadError) return <div className="settings-section-error">{loadError}</div>;
  if (!current) return null;

  async function save(enabled: boolean) {
    setBusy(true);
    setErrorText("");
    try {
      setCurrent(await patchToolsNetwork(enabled));
    } catch (error) {
      setErrorText(instanceError(error).detail);
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <div className="administration-card tools-network-card">
      <div className="settings-card-head">
        <div>
          <strong>{t("settings.tools_network_title")}</strong>
          <small>{t("settings.tools_network_hint")}</small>
        </div>
        <SwitchButton
          checked={current.enabled}
          className="ui-switch"
          disabled={busy}
          label={t("settings.tools_network_title")}
          onClick={() => (current.enabled ? void save(false) : setConfirming(true))}
        />
      </div>
      <p className="settings-section-note">
        {t(current.enabled ? "settings.tools_network_lead_on" : "settings.tools_network_lead_off")}
      </p>
      <div className="settings-risk-note">
        <Icon name="alert" size={16} strokeWidth={1.9} />
        <p>
          {t("settings.tools_network_risk_before")} <b>{t("settings.tools_network_risk_emphasis")}</b>{" "}
          {t("settings.tools_network_risk_after", { organization: organizationName })}
        </p>
      </div>
      <p className="tools-network-closed">
        <Icon name="lock" size={13} strokeWidth={2} />
        <span>{t("settings.tools_network_always_closed")}</span>
      </p>
      {errorText && <div className="administration-message error" role="alert">{errorText}</div>}
      <div className="administration-actions">
        <small className="administration-saved">{savedLabel(current)}</small>
      </div>
      <DecisionDialog
        open={confirming}
        tone="warning"
        icon="alert"
        title={t("settings.tools_network_confirm_title")}
        description={t("settings.tools_network_confirm_text")}
        onClose={() => setConfirming(false)}
        actions={(
          <>
            <Button variant="secondary" disabled={busy} onClick={() => setConfirming(false)}>{t("common.cancel")}</Button>
            <Button variant="primary" disabled={busy} onClick={() => void save(true)}>{t("settings.tools_network_allow")}</Button>
          </>
        )}
      >
        <div className="settings-risk-note">
          <p>
            {t("settings.tools_network_confirm_risk_before")} <b>{t("settings.tools_network_confirm_risk_emphasis")}</b>
            {t("settings.tools_network_confirm_risk_after")}
          </p>
        </div>
      </DecisionDialog>
    </div>
  );
}
