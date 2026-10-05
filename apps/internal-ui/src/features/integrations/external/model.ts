import { t } from "../../../i18n";
import type { Integration } from "../model";
import type { ParameterSource, ServerDraft, ServerKind, ToolParameter } from "./types";

export function serverDraft(kind: ServerKind, integration?: Integration | null): ServerDraft {
  const stored = integration?.externalServer;
  return { name: integration?.name ?? "", isActive: integration?.isActive ?? true,
    externalServer: stored ? { type: stored.type, url: stored.url, description: stored.description,
      headers: stored.headers.map((h) => ({ ...h, saved: h.secret })),
      ...(kind === "http" ? { method: stored.method, toolName: stored.toolName, readOnly: stored.readOnly,
        parameters: stored.parameters?.map((p) => ({ ...p, source: { ...p.source } })) } : {}) }
      : { type: kind, description: "", url: "", headers: [],
        ...(kind === "http" ? { method: "GET", toolName: "", readOnly: false, parameters: [] } : {}) } };
}

export function serverHost(address: string): string {
  try { return new URL(address).host; } catch { return ""; }
}

export function sourceKey(source: ParameterSource): string {
  if (source.type === "contact") return `contact:${source.field}`;
  if (source.type === "web_field") return `web:${source.integrationId}:${source.key}`;
  return "ai";
}

export function sourceFromKey(key: string): ParameterSource {
  const [kind, id, field] = key.split(":");
  if (kind === "contact" && ["name", "email", "phone"].includes(id)) return { type: "contact", field: id as "name" | "email" | "phone" };
  if (kind === "web" && Number(id) > 0 && field) return { type: "web_field", integrationId: Number(id), key: field };
  return { type: "ai" };
}

export function sourceLabel(source: ParameterSource, integrations: Integration[]): string {
  if (source.type === "ai") return t("servers.ai_source");
  if (source.type === "contact") return t(source.field === "name" ? "common.name" : source.field === "email" ? "site_fields.email" : "site_fields.phone");
  return integrations.find((i) => i.id === source.integrationId)?.config.fields?.find((f) => f.key === source.key)?.label ?? t("servers.field_missing");
}

export function blankParameter(): ToolParameter {
  return { name: "", type: "string", description: "", required: false, location: "query", source: { type: "ai" } };
}

export function duplicateParameter(parameters: ToolParameter[], index: number): ToolParameter[] {
  const item = parameters[index];
  let suffix = 2;
  let name: string;
  do { name = `${item.name.slice(0, 34)}_${suffix++}`; } while (parameters.some((p) => p.name === name));
  const next = [...parameters];
  next.splice(index + 1, 0, { ...item, name, location: item.location === "path" ? "query" : item.location, source: { ...item.source } });
  return next;
}

export function moveParameter(parameters: ToolParameter[], index: number, offset: number): ToolParameter[] {
  const to = index + offset;
  if (to < 0 || to >= parameters.length) return parameters;
  const next = [...parameters];
  next.splice(to, 0, next.splice(index, 1)[0]);
  return next;
}
