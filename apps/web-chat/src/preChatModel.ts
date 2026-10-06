import type { WebConfig } from "./api";
import { t } from "./i18n";
import type { ClientFieldType, ClientField } from "@chatballs/shared";
export { inputValue, validField, formPayload } from "@chatballs/shared";

export type FieldType = ClientFieldType;
export type FieldSchema = ClientField;
export type PreChatConfig = { enabled: boolean; title: string; fields: { key: string; required: boolean }[] };
export type PreChatField = FieldSchema & { required: boolean };

export function preChatFields(config: WebConfig): PreChatField[] {
  const schema: FieldSchema[] = [
    { key: "name", label: t("pre_chat.name"), type: "string" },
    { key: "email", label: t("pre_chat.email"), type: "email" },
    { key: "phone", label: t("pre_chat.phone"), type: "phone" },
    ...(config.fields ?? []),
  ];
  return (config.preChat?.fields ?? []).flatMap((selected) => {
    const field = schema.find((item) => item.key === selected.key);
    return field ? [{ ...field, required: selected.required }] : [];
  });
}
