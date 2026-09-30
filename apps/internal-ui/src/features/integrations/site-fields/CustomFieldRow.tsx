import { Dropdown } from "antd";
import { t } from "../../../i18n";
import { SelectField, SwitchButton } from "../../../shared/form-controls";
import { Icon } from "../../../shared/icons";
import { fieldTypeOptions, type FieldType, type SiteField } from "./model";
import { FieldTypeIcon } from "./FieldTypeIcon";

export function CustomFieldRow({ field, disabled, onChange, onRename, onDelete, onOption, onDrag, onDrop, onDragEnd, onMove }: {
  field: SiteField;
  disabled: boolean;
  onChange: (field: SiteField) => void;
  onRename: () => void;
  onDelete: () => void;
  onOption: (index?: number) => void;
  onDrag: () => void;
  onDrop: () => void;
  onDragEnd: () => void;
  onMove: (direction: number) => void;
}) {
  return <tr data-field-key={field.key} className={field.type === "enum" ? "has-options" : ""}
    onDragOver={(event) => { if (!disabled) event.preventDefault(); }}
    onDrop={(event) => { event.preventDefault(); if (!disabled) onDrop(); }}>
    <td><button type="button" className="site-field-grip" draggable={!disabled} disabled={disabled}
      aria-label={t("site_fields.reorder", { label: field.label })}
      onDragStart={(event) => { event.dataTransfer.setData("text/plain", field.key); onDrag(); }} onDragEnd={onDragEnd}
      onKeyDown={(event) => {
        if (event.key === "ArrowUp" || event.key === "ArrowDown") {
          event.preventDefault(); onMove(event.key === "ArrowUp" ? -1 : 1);
        }
      }}><Icon name="grip" size={14} /></button></td>
    <td><code>{field.key}</code></td>
    <td><span className="site-field-label">{field.label}</span>
      {field.type === "enum" && <div className="site-field-options">
        {field.options?.map((option, index) => <button className="site-field-option" type="button" key={option.value}
          disabled={disabled} onClick={() => onOption(index)}>
          <i style={{ background: option.color || "var(--n-5)" }} />{option.label}<code>· {option.value}</code>
        </button>)}
        <button className="site-field-add-option" type="button" disabled={disabled} onClick={() => onOption()}>{t("site_fields.add_option")}</button>
      </div>}
    </td>
    <td><SelectField label={t("site_fields.type")} adornment={<FieldTypeIcon type={field.type} />}
      disabled={disabled} options={fieldTypeOptions} value={field.type} onChange={(type) => {
        const { options, ...rest } = field;
        onChange({ ...rest, type: type as FieldType, ...(type === "enum" ? { options: options ?? [] } : {}) });
      }} /></td>
    <td><SwitchButton className="ui-switch is-compact" label={`${t("site_fields.ai")}: ${field.label}`}
      disabled={disabled} checked={field.aiVisible} onClick={() => onChange({ ...field, aiVisible: !field.aiVisible })} /></td>
    <td><Dropdown trigger={["click"]} overlayClassName="app-dropdown" menu={{ items: [
      { key: "rename", label: t("site_fields.rename"), onClick: onRename },
      { key: "delete", label: t("common.delete"), danger: true, onClick: onDelete },
    ] }}><button className="row-menu-button" type="button" disabled={disabled} aria-label={`${t("common.actions")}: ${field.label}`}><Icon name="more" size={16} /></button></Dropdown></td>
  </tr>;
}
