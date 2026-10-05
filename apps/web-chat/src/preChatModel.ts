import type { SiteFields, WebConfig } from "./api";
import { t } from "./i18n";
import { formatPhone, validPhone } from "./phoneFormat";

export type FieldType = "string" | "number" | "boolean" | "datetime" | "enum" | "email" | "phone" | "url";
export type FieldSchema = { key: string; label: string; type: FieldType; options?: { value: string; label: string }[] };
export type PreChatConfig = { enabled: boolean; title: string; fields: { key: string; required: boolean }[] };
export type PreChatField = FieldSchema & { required: boolean };

function validEmail(text: string): boolean {
  const parts = text.split("@");
  if (parts.length !== 2) return false;
  const [local, domain] = parts;
  if (!local || local.startsWith(".") || local.endsWith(".") || local.includes("..")) return false;
  return /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local)
    && domain.includes(".")
    && domain.split(".").every((part) => /^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$/.test(part));
}

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

export function inputValue(field: PreChatField, value: SiteFields[string] | undefined): string | boolean {
  if (field.type === "boolean") return typeof value === "boolean" ? value : "";
  if (value == null) return "";
  const text = String(value);
  if (field.type === "phone") return formatPhone(text);
  if (field.type === "datetime" && text && !Number.isNaN(Date.parse(text))) {
    const date = new Date(text);
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return local.toISOString().slice(0, 16);
  }
  return text;
}

export function validField(field: PreChatField, value: string | boolean): boolean {
  if (typeof value === "boolean") return field.type === "boolean";
  const text = value.trim();
  if (!text) return !field.required;
  if (text.length > 500) return false;
  switch (field.type) {
    case "email": return validEmail(text);
    case "phone": return validPhone(text);
    case "boolean": return false;
    case "enum": return Boolean(field.options?.some((option) => option.value === text));
    case "datetime": return !Number.isNaN(Date.parse(text));
    case "number": return Number.isFinite(Number(text));
    case "url": {
      try { return ["http:", "https:"].includes(new URL(text).protocol); } catch { return false; }
    }
    default: return true;
  }
}

export function formPayload(fields: PreChatField[], values: Record<string, string | boolean>): SiteFields {
  return Object.fromEntries(fields.map((field) => {
    const value = values[field.key];
    if (typeof value === "boolean") return [field.key, value];
    const text = (value ?? "").trim();
    return [field.key, !text ? null : field.type === "number" ? Number(text) : text];
  }));
}
