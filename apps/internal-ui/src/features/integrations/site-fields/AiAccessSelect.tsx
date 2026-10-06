import { useState } from "react";
import { t } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { SelectMenu, type SelectOption } from "../../../shared/ui-controls";
import { AI_ACCESS_MODES, aiAccessIcons, isMaskOnly, type AiAccess, type SiteField } from "./model";

/** Выбор «Доступ AI» в строке своего поля (кадр W1). */
export function AiAccessSelect({ field, disabled, onChange }: {
  field: SiteField;
  disabled: boolean;
  onChange: (access: AiAccess) => void;
}) {
  const [open, setOpen] = useState(false);
  const maskOnly = isMaskOnly(field.type);
  const options: SelectOption[] = AI_ACCESS_MODES.map((mode) => {
    const locked = maskOnly && mode === "open";
    return { value: mode, label: t(`site_fields.ai_${mode}`), icon: aiAccessIcons[mode], disabled: locked,
      hint: locked ? t("site_fields.ai_mask_only_reason") : t(`site_fields.ai_${mode}_hint`) };
  });
  return <div className="readonly-field select-like site-field-access">
    <SelectMenu disabled={disabled} open={open} onOpenChange={setOpen} options={options} selected={[field.aiAccess]}
      overlayClassName="app-dropdown is-ai-access" placement="bottomRight"
      onSelect={(mode) => { onChange(mode as AiAccess); setOpen(false); }}>
      <button className="select-box" type="button" disabled={disabled} aria-label={`${t("site_fields.ai_access")}: ${field.label}`}>
        <Icon name={aiAccessIcons[field.aiAccess]} size={13} strokeWidth={1.9} />
        <span className="select-value">{t(`site_fields.ai_${field.aiAccess}`)}</span>
        <Icon name="chevron" size={14} strokeWidth={2.2} />
      </button>
    </SelectMenu>
    {maskOnly && <small className="site-field-access-note">{t("site_fields.ai_mask_only")}</small>}
  </div>;
}
