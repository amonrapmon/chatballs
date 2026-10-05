import { Dropdown } from "antd";
import { t } from "../../../i18n";
import { SwitchButton } from "../../../shared/form-controls";
import { Icon } from "../../../shared/icons";
import type { SiteField } from "../site-fields/model";
import { CONTACT_KEYS, type PreChatField } from "./model";

export function PreChatFields({ fields, customFields, remainingFields, disabled, onSelect, onRequired, onAdd }: {
  fields: PreChatField[];
  customFields: SiteField[];
  remainingFields: SiteField[];
  disabled: boolean;
  onSelect: (key: string, selected: boolean) => void;
  onRequired: (key: string, required: boolean) => void;
  onAdd: (key: string) => void;
}) {
  const rows = [
    ...CONTACT_KEYS.map((key) => ({ key, label: t(`pre_chat.${key}`), custom: false })),
    ...customFields.map(({ key, label }) => ({ key, label, custom: true })),
  ];
  return <div className="pre-chat-fields">
    <div className="pre-chat-fields-head"><span /><span>{t("pre_chat.field")}</span><span>{t("pre_chat.source")}</span><span>{t("pre_chat.required")}</span></div>
    {rows.map((row) => {
      const selected = fields.find(({ key }) => key === row.key);
      return <div key={row.key} data-field-key={row.key} className={`pre-chat-field-row${selected ? "" : " is-off"}`}>
        <label className="pre-chat-check">
          <input type="checkbox" aria-label={row.label} checked={Boolean(selected)} disabled={disabled}
            onChange={(event) => onSelect(row.key, event.target.checked)} />
          <span>{selected && <Icon name="check" size={12} strokeWidth={3} />}</span>
        </label>
        <span className="pre-chat-field-label"><strong>{row.label}</strong>{row.custom && <small>{t("pre_chat.custom")}</small>}</span>
        <span className="pre-chat-source">{row.key === "name" || row.key === "email" ? t("pre_chat.site_source", { key: row.key }) : row.key}</span>
        <SwitchButton className="ui-switch is-compact" label={t("pre_chat.required_label", { label: row.label })}
          disabled={disabled || !selected} checked={selected?.required ?? false} onClick={() => onRequired(row.key, !selected?.required)} />
      </div>;
    })}
    <div className="pre-chat-fields-footer">
      <Dropdown trigger={["click"]} overlayClassName="app-dropdown" disabled={disabled || !remainingFields.length}
        menu={{ items: remainingFields.map(({ key, label }) => ({ key, label, onClick: () => onAdd(key) })) }}>
        <button className="row-menu-button" type="button" disabled={disabled || !remainingFields.length}>
          <Icon name="plus" size={14} />{t("pre_chat.add_custom")}
        </button>
      </Dropdown>
      <small>{t("pre_chat.types_hint")}</small>
    </div>
  </div>;
}
