import { Switch } from "antd";
import type { PreChatField as Field } from "./preChatModel";
import { formatPhone } from "./phoneFormat";
import { t } from "./i18n";
import { widgetClasses as classes } from "./widgetClasses";

export function PreChatField({ field, value, fromSite, onChange }: {
  field: Field;
  value: string | boolean;
  fromSite: boolean;
  onChange: (value: string | boolean) => void;
}) {
  const id = `pre-chat-${field.key}`;
  return (
    <div>
      <label htmlFor={id} className={classes.preChatLabel}>
        {field.label}
        {field.required && <span className={classes.preChatRequired} aria-hidden="true">*</span>}
        {fromSite && <small className={classes.preChatSource}>{t("pre_chat.from_site")}</small>}
      </label>
      {field.type === "boolean"
        ? <Switch id={id} checked={value === true} onChange={onChange} aria-label={field.label} aria-required={field.required} />
        : field.type === "enum"
          ? <select id={id} className={classes.preChatInput} data-from-site={fromSite} value={String(value)} required={field.required} onChange={(event) => onChange(event.target.value)}>
              <option value="" />
              {field.options?.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          : <input id={id} className={classes.preChatInput} data-from-site={fromSite}
              type={field.type === "datetime" ? "datetime-local" : field.type === "email" ? "email" : field.type === "phone" ? "tel" : "text"}
              inputMode={field.type === "phone" ? "tel" : field.type === "number" ? "decimal" : undefined}
              value={String(value)} required={field.required} maxLength={500}
              placeholder={field.type === "phone" ? t("pre_chat.phone_placeholder") : undefined}
              onChange={(event) => onChange(field.type === "phone" ? formatPhone(event.target.value) : event.target.value)} />}
    </div>
  );
}
