import { useEffect } from "react";
import { t } from "../../../i18n";
import { SwitchButton } from "../../../shared/form-controls";
import type { Integration } from "../model";
import { PreChatFields } from "./PreChatFields";
import { PreChatText } from "./PreChatText";
import { usePreChat } from "./usePreChat";
import "./styles.css";

export function PreChatSection({ integration, onSaved, onEnabled }: {
  integration: Integration;
  onSaved: (integration: Integration) => void;
  onEnabled: (enabled: boolean) => void;
}) {
  const state = usePreChat(integration, onSaved);
  const { preChat } = state.draft;
  useEffect(() => onEnabled(preChat.enabled), [preChat.enabled, onEnabled]);
  return <div className="pre-chat-section">
    <div className="portal-settings-heading"><h3>{t("settings.pre_chat_form")}</h3><p>{t("pre_chat.description")}</p></div>
    <div className="portal-settings-card pre-chat-enable">
      <span><strong>{t("pre_chat.enabled")}</strong><small>{t("pre_chat.disabled_hint")}</small></span>
      <SwitchButton className="ui-switch" label={t("pre_chat.enabled")} disabled={state.busy} checked={preChat.enabled}
        onClick={() => state.change({ preChat: { ...preChat, enabled: !preChat.enabled } })} />
    </div>
    <PreChatFields fields={preChat.fields} customFields={state.customFields} remainingFields={state.remainingFields} disabled={state.busy}
      onSelect={state.select} onAdd={state.add} onRequired={(key, required) => state.change({
        preChat: { ...preChat, fields: preChat.fields.map((field) => field.key === key ? { ...field, required } : field) },
      })} />
    <PreChatText draft={state.draft} version={integration.config.consentVersion} updatedAt={integration.updatedAt}
      busy={state.busy} error={state.error} onChange={state.change} onSave={() => void state.save()} />
  </div>;
}
