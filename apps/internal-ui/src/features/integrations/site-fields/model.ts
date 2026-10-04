import { ApiError } from "../../../api/client";
import { t } from "../../../i18n";
import type { Icon } from "../../../shared/icons";

export const FIELD_TYPES = ["string", "number", "boolean", "datetime", "enum", "email", "phone", "url"] as const;
export type FieldType = typeof FIELD_TYPES[number];
export const AI_ACCESS_MODES = ["hidden", "masked", "open"] as const;
export type AiAccess = typeof AI_ACCESS_MODES[number];
export type FieldOption = { value: string; label: string; color?: string };
export type SiteField = {
  id?: string;
  key: string;
  label: string;
  type: FieldType;
  options?: FieldOption[];
  aiAccess: AiAccess;
  order: number;
};
export const fieldTypeOptions = FIELD_TYPES.map((type): [string, string] => [type, t(`site_fields.${type}`)]);
export const fieldIcons: Record<FieldType, Parameters<typeof Icon>[0]["name"]> = {
  string: "text", number: "numlist", boolean: "check", datetime: "clock",
  enum: "list", email: "mail", phone: "phone", url: "link",
};
export const aiAccessIcons: Record<AiAccess, Parameters<typeof Icon>[0]["name"]> = { hidden: "eyeOff", masked: "mask", open: "eye" };

/** Почта и телефон уходят AI только под маской: открыть их значение сервер не даст. */
export const isMaskOnly = (type: FieldType): boolean => type === "email" || type === "phone";

/** Режим доступа, допустимый для типа: при смене типа на почту или телефон «Видит значение» становится маской. */
export const aiAccessFor = (type: FieldType, access: AiAccess): AiAccess =>
  isMaskOnly(type) && access === "open" ? "masked" : access;

export function fieldError(field: SiteField, fields: SiteField[], creating: boolean): string | undefined {
  if (!field.label.trim() || field.label.trim().length > 60) return t("site_fields.label_invalid");
  if (!creating) return undefined;
  if (fields.length >= 30) return t("site_fields.limit");
  if (!/^[a-z][a-z0-9_]{0,39}$/.test(field.key)) return t("site_fields.key_invalid");
  if (["name", "email", "phone"].includes(field.key)) return t("site_fields.key_reserved");
  if (fields.some((item) => item.key === field.key)) return t("site_fields.key_duplicate");
}

export function optionError(option: FieldOption, options: FieldOption[], index?: number): string | undefined {
  if (!option.value.trim() || !option.label.trim() || option.label.trim().length > 60
    || (option.color && !/^#[\da-f]{6}$/i.test(option.color))) return t("site_fields.option_invalid");
  if (options.some((item, position) => position !== index && item.value === option.value.trim())) return t("site_fields.option_duplicate");
}

export const orderedFields = (fields: SiteField[]): SiteField[] =>
  [...fields].sort((a, b) => a.order - b.order).map((field, order) => ({ ...field, order }));

export function moveField(fields: SiteField[], from: string, to: string): SiteField[] {
  const result = [...fields];
  const start = result.findIndex((field) => field.key === from);
  const end = result.findIndex((field) => field.key === to);
  if (start < 0 || end < 0) return fields;
  result.splice(end, 0, result.splice(start, 1)[0]);
  return result.map((field, order) => ({ ...field, order }));
}

export function fieldsSaveError(error: unknown): string {
  // Only the server's user-facing validation message may reach the UI.
  return error instanceof ApiError && error.status === 400
    ? error.message : t("common.could_not_save");
}

function exampleValue(field: SiteField): unknown {
  if (field.type === "boolean") return true;
  if (field.type === "number") return 42;
  if (field.type === "datetime") return "2026-09-30T12:00:00Z";
  if (field.type === "enum") return (field.key === "order_status"
    ? field.options?.find((option) => option.value === "cooking")?.value : undefined)
    ?? field.options?.[0]?.value ?? null;
  if (field.type === "email") return "irina.sokolova@mail.ru";
  if (field.type === "phone") return "+79991234567";
  if (field.type === "url") return "https://example.com";
  if (field.key === "user_id") return "u_58213";
  if (field.key === "order_number") return "10482";
  return t("site_fields.example_value");
}

export function fieldsSnippet(fields: SiteField[]): string {
  const values = { name: t("site_fields.example_name"), email: "irina.sokolova@mail.ru",
    ...Object.fromEntries(fields.map((field) => [field.key, exampleValue(field)])) };
  const lines = Object.entries(values).map(([key, value]) => `  ${key}: ${JSON.stringify(value)}`);
  const updated = fields.find((field) => field.type === "enum" && (field.options?.length ?? 0) > 1);
  const updateKey = updated?.key ?? fields[0]?.key ?? "name";
  const updateValue = updated
    ? (updated.key === "order_status" ? updated.options?.find((option) => option.value === "on_the_way")?.value : undefined)
      ?? updated.options![1].value
    : null;
  const comment = t(updated?.key === "order_status" ? "site_fields.status_comment" : "site_fields.update_comment");
  return `Chatballs.setFields({\n${lines.join(",\n")}\n});\n\n// ${comment}\nChatballs.setFields({ ${updateKey}: ${JSON.stringify(updateValue)} });`;
}
