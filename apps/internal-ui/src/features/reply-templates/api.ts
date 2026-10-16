import { api } from "../../api/client";
import type { ReplyTemplateRef } from "../conversations/model";

export type TemplateScope = "PERSONAL" | "SHARED";
export type TaxonomyKind = "categories" | "tags";
export type TemplateTaxon = { id: number; name: string; scope: TemplateScope; ownerId: number | null };
export type TemplateVariable = { key: string; token: string; label: string; type: string; connectionName?: string };
export type TemplatePermissions = { canManageShared: boolean; canGrantSharedManagement: boolean };
export type TemplateDraft = { title: string; text?: string; scope: TemplateScope; categoryId: number | null; tagIds: number[] };
export type TemplatePage = { items: ReplyTemplateRef[]; page: number; pageCount: number; total: number; pageSize: number };
export type TemplateFilters = { scope?: TemplateScope; q?: string; categoryId?: number | null; tagIds?: number[]; page?: number };
const base = "/api/v1/conversations/templates/";

export function searchTemplates(filters: TemplateFilters) {
  const params = new URLSearchParams({ q: filters.q ?? "", page: String(filters.page ?? 1) });
  if (filters.scope) params.set("scope", filters.scope);
  if (filters.categoryId) params.set("categoryId", String(filters.categoryId));
  if (filters.tagIds?.length) params.set("tagIds", filters.tagIds.join(","));
  return api<TemplatePage>(`${base}?${params}`);
}
export const templatePermissions = () => api<TemplatePermissions>(`${base}permissions/`);
export const templateVariables = () => api<{ items: TemplateVariable[] }>(`${base}variables/`).then(r => r.items);
export const templateTaxonomy = (kind: TaxonomyKind) => api<{ items: TemplateTaxon[] }>(`${base}${kind}/`).then(r => r.items);
export const saveTemplate = (id: number | undefined, draft: TemplateDraft) => api(`${base}${id ? `${id}/` : ""}`, {
  method: id ? "PATCH" : "POST", body: JSON.stringify(draft),
});
export const saveTaxon = (kind: TaxonomyKind, scope: TemplateScope, name: string, id?: number) => api(`${base}${kind}/${id ? `${id}/` : ""}`, {
  method: id ? "PATCH" : "POST", body: JSON.stringify(id ? { name } : { name, scope }),
});
export const deleteTaxon = (kind: TaxonomyKind, id: number) => api(`${base}${kind}/${id}/`, { method: "DELETE" });
export const renderReplyTemplate = (id: number, conversationId: number) => api<{ text: string; unfilledKeys: string[] }>(`${base}${id}/render/`, {
  method: "POST", body: JSON.stringify({ conversationId }),
});
export type TemplateGrant = { membershipId: number; canManageShared: boolean; granted: boolean };
export const templateGrant = (membershipId: number) => api<TemplateGrant>(`${base}permissions/${membershipId}/`);
export const setTemplateGrant = (membershipId: number, granted: boolean) => api<TemplateGrant>(`${base}permissions/${membershipId}/`, {
  method: "PATCH", body: JSON.stringify({ granted }),
});
