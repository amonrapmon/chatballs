import { Switch } from "antd";
import { formatPhone, type ClientField } from "@chatballs/shared";

/** The same typed inputs in the pre-chat form and the agent test panel. */
export function ClientFieldControl({ field, id, value, onChange, className, required = false,
  disabled = false, fromSite = false, phonePlaceholder }: {
  field: ClientField;
  id: string;
  value: string | boolean;
  onChange: (value: string | boolean) => void;
  className?: string;
  required?: boolean;
  disabled?: boolean;
  fromSite?: boolean;
  phonePlaceholder?: string;
}) {
  if (field.type === "boolean") return <Switch id={id} checked={value === true} disabled={disabled}
    onChange={onChange} aria-label={field.label} aria-required={required} />;
  if (field.type === "enum") return <select id={id} className={className} data-from-site={fromSite}
    value={String(value)} required={required} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
    <option value="" />
    {field.options?.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
  </select>;
  return <input id={id} className={className} data-from-site={fromSite}
    type={field.type === "datetime" ? "datetime-local" : field.type === "email" ? "email" : field.type === "phone" ? "tel" : "text"}
    inputMode={field.type === "phone" ? "tel" : field.type === "number" ? "decimal" : undefined}
    value={String(value)} required={required} disabled={disabled} maxLength={500}
    placeholder={field.type === "phone" ? phonePlaceholder : undefined}
    onChange={(event) => onChange(field.type === "phone" ? formatPhone(event.target.value) : event.target.value)} />;
}
