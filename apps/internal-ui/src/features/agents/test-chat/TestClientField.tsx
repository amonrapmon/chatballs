import { useState } from "react";
import { ClientFieldControl } from "@chatballs/ui";
import type { ClientField } from "@chatballs/shared";
import { t } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { SelectMenu } from "../../../shared/ui-controls";

export function TestClientField({ field, id, value, onChange, disabled }: {
  field: ClientField; id: string; value: string | boolean; disabled: boolean;
  onChange: (value: string | boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = field.options?.find((option) => option.value === value);
  return <div className="agent-test-field">
    <label htmlFor={id}>{field.label}</label>
    {field.type === "enum" ? <SelectMenu open={open} onOpenChange={setOpen} disabled={disabled}
      selected={[String(value)]} options={[{ value: "", label: "" }, ...(field.options ?? []).map((option) => ({ ...option, dot: option.color }))]}
      onSelect={(next) => { onChange(next); setOpen(false); }}>
      <button type="button" id={id} className="row-menu-button agent-test-input agent-test-select" disabled={disabled}
        aria-label={field.label} aria-haspopup="menu" aria-expanded={open}>
        <span>{selected?.color && <i style={{ background: selected.color }} />}{selected?.label}</span>
        <Icon name="chevron" size={13} strokeWidth={2} />
      </button>
    </SelectMenu> : <ClientFieldControl field={field} id={id} className="agent-test-input" value={value}
      disabled={disabled} onChange={onChange} phonePlaceholder={t("agent_test.phone_placeholder")} />}
  </div>;
}
