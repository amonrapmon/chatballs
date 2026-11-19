import { useId } from "react";
import { t } from "../../i18n";
import { SwitchButton } from "../../shared/form-controls";
import type { ConnectorSettings } from "./model";
import "./styles.css";

export function ConnectorOptions({ value, onChange, disabled }: {
  value: ConnectorSettings; onChange: (value: ConnectorSettings) => void; disabled: boolean;
}) {
  const descriptionId = useId();
  const mirror = t("settings.connector_mirror_outgoing");
  const aiOutbound = t("settings.connector_ai_outbound");

  return (
    <section className="integration-connector-options" aria-label={t("settings.connector_behavior")}>
      <h3>{t("settings.connector_behavior")}</h3>
      <div className="integration-connector-options__row">
        <span className="integration-connector-options__copy">
          <strong>{mirror}</strong>
          <small id={descriptionId}>{t("settings.connector_mirror_outgoing_help")}</small>
        </span>
        <SwitchButton className="ui-switch" label={mirror} describedBy={descriptionId}
          checked={value.mirrorExternalOutgoingEnabled} disabled={disabled}
          onClick={() => onChange({ ...value, mirrorExternalOutgoingEnabled: !value.mirrorExternalOutgoingEnabled })} />
      </div>
      <div className="integration-connector-options__row">
        <span className="integration-connector-options__copy">
          <strong>{aiOutbound}</strong>
          <small>{t("settings.connector_ai_outbound_help")}</small>
        </span>
        <SwitchButton className="ui-switch" label={aiOutbound} checked={value.connectorAiOutboundEnabled} disabled={disabled}
          onClick={() => onChange({ ...value, connectorAiOutboundEnabled: !value.connectorAiOutboundEnabled })} />
      </div>
    </section>
  );
}

export function VkMirrorOption({ enabled, onChange, disabled }: {
  enabled: boolean; onChange: (enabled: boolean) => void; disabled: boolean;
}) {
  const descriptionId = useId();
  const label = t("settings.vk_native_mirror");
  return (
    <section className="integration-connector-options" aria-label={label}>
      <div className="integration-connector-options__row">
        <span className="integration-connector-options__copy">
          <strong>{label}</strong>
          <small id={descriptionId}>{t("settings.vk_native_mirror_help")}</small>
        </span>
        <SwitchButton className="ui-switch" label={label} describedBy={descriptionId}
          checked={enabled} disabled={disabled} onClick={() => onChange(!enabled)} />
      </div>
    </section>
  );
}
