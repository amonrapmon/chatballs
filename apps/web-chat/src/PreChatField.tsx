import { ClientFieldControl } from "@chatballs/ui";
import type { PreChatField as Field } from "./preChatModel";
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
      <ClientFieldControl field={field} id={id} value={value} onChange={onChange}
        className={classes.preChatInput} required={field.required} fromSite={fromSite}
        phonePlaceholder={t("pre_chat.phone_placeholder")} />
    </div>
  );
}
