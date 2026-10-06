import { formatPhone, validPhone } from "./phoneFormat";

export type ClientFieldType = "string" | "number" | "boolean" | "datetime" | "enum" | "email" | "phone" | "url";
export type ClientField = { key: string; label: string; type: ClientFieldType; options?: { value: string; label: string; color?: string }[]; required?: boolean };

function validEmail(text: string): boolean {
  const parts = text.split("@");
  if (parts.length !== 2) return false;
  const [local, domain] = parts;
  if (!local || local.startsWith(".") || local.endsWith(".") || local.includes("..")) return false;
  return /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local)
    && domain.includes(".")
    && domain.split(".").every((part) => /^[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$/.test(part));
}

export function inputValue(field: ClientField, value: string | number | boolean | null | undefined): string | boolean {
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

export function validField(field: ClientField, value: string | boolean): boolean {
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

export function formPayload(fields: ClientField[], values: Record<string, string | boolean>): Record<string, string | number | boolean | null> {
  return Object.fromEntries(fields.map((field) => {
    const value = values[field.key];
    if (typeof value === "boolean") return [field.key, value];
    const text = (value ?? "").trim();
    return [field.key, !text ? null : field.type === "number" ? Number(text) : text];
  }));
}
