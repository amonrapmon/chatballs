import type { SiteField } from "@chatballs/contracts";

export const RECENT_SITE_FIELD_MS = 10 * 60 * 1000;

export function isRecentSiteField(field: SiteField, now: number): boolean {
  const updated = Date.parse(field.updatedAt);
  return updated <= now && now < updated + RECENT_SITE_FIELD_MS;
}

export function nextSiteFieldExpiry(fields: readonly SiteField[], now: number): number | undefined {
  const expiries = fields.map((field) => Date.parse(field.updatedAt) + RECENT_SITE_FIELD_MS)
    .filter((expiry) => expiry > now);
  return expiries.length ? Math.min(...expiries) : undefined;
}

export function isSiteIdentifier(field: SiteField): boolean {
  return field.type === "number" || (field.type === "string"
    && (/(^|_)(id|number)($|_)/i.test(field.key) || /^\d+$/.test(String(field.value))));
}

export function siteFieldHref(field: SiteField): string | undefined {
  if (field.type === "email") return `mailto:${field.value}`;
  if (field.type === "phone") return `tel:${String(field.value).replace(/[^+\d]/g, "")}`;
  if (field.type === "url" && /^https?:\/\//i.test(String(field.value))) return String(field.value);
  return undefined;
}
