import { api, ApiError } from "../../api/client";
import { t } from "../../i18n";
import type { PagedPayload } from "../../shared/usePagedResource";

export type SkillTemplate = {
  id: string;
  name: string;
  purpose: string;
  schema: Record<string, unknown>;
  html: string;
  css: string;
  text: string;
  examples: Record<string, unknown>[];
};
export type Configuration = { name: string; description: string; instruction: string; templates: SkillTemplate[] };
export type Skill = {
  id: string;
  name: string;
  description: string;
  revision: number;
  templates: Pick<SkillTemplate, "id" | "name" | "purpose">[];
  templateCount: number;
  agents: { id: number; aiAgentId: number; name: string }[];
  agentCount: number;
  createdBy: { id: number; name: string } | null;
  updatedBy: { id: number; name: string } | null;
  createdAt: string;
  updatedAt: string;
};
export type SkillDetail = Omit<Skill, "templates"> & Configuration;
export const emptyConfiguration = (): Configuration => ({ name: "", description: "", instruction: "", templates: [] });
export const configurationOf = (skill: SkillDetail): Configuration => ({
  name: skill.name,
  description: skill.description,
  instruction: skill.instruction,
  templates: skill.templates,
});
const base = "/api/v1/skills/";
export const listSkills = (page = 1, query = "", agentId = "") =>
  api<PagedPayload<Skill> & { connectedAgentCount: number }>(
    `${base}?${new URLSearchParams({ page: String(page), q: query, ...(agentId ? { agentId } : {}) })}`,
  );
export const getSkill = (id: string) => api<{ skill: SkillDetail }>(`${base}${id}/`);
export const getDeletion = (id: string) => api<{ skill: Skill }>(`${base}${id}/deletion/`);
export const getOrdersBasis = () => api<{ configuration: Configuration }>(`${base}bases/orders/`);
export type SaveRequest = { requestId: string; configuration: Configuration; expectedRevision?: number };
export const saveSkill = (id: string | null, body: SaveRequest) =>
  api<{ skill: SkillDetail }>(id ? `${base}${id}/` : base, {
    method: id ? "PUT" : "POST",
    body: JSON.stringify(body),
  });
export const deleteSkill = (skill: Skill) =>
  api<void>(`${base}${skill.id}/`, {
    method: "DELETE",
    body: JSON.stringify({ expectedRevision: skill.revision }),
  });
export const assignSkill = (skill: Skill, agentId: number, enabled: boolean) =>
  api<{ skill: Skill }>(`${base}${skill.id}/agents/${agentId}/`, {
    method: enabled ? "PUT" : "DELETE",
    body: JSON.stringify({ expectedRevision: skill.revision }),
  });
export const isConflict = (error: unknown) => error instanceof ApiError && error.status === 409;
export const skillError = (error: unknown) =>
  isConflict(error)
    ? t("skills.conflict")
    : error instanceof ApiError && error.status < 500
      ? error.message
      : t("skills.action_error");
export function validateConfiguration(config: Configuration) {
  const errors: Partial<Record<"name" | "description" | "instruction", string>> = {};
  for (const [field, limit] of [
    ["name", 60],
    ["description", 200],
    ["instruction", 32768],
  ] as const) {
    if (!config[field].trim()) errors[field] = t("skills.required");
    else if (Array.from(config[field]).length > limit) errors[field] = t("skills.too_long", { count: limit });
  }
  return errors;
}

// Preserve the body/key after an uncertain result. An edited body is a new action.
export function requestFor(
  config: Configuration,
  revision: number | undefined,
  previous: SaveRequest | null,
): SaveRequest {
  if (
    previous &&
    JSON.stringify(previous.configuration) === JSON.stringify(config) &&
    previous.expectedRevision === revision
  )
    return previous;
  return {
    requestId: crypto.randomUUID(),
    configuration: structuredClone(config),
    ...(revision ? { expectedRevision: revision } : {}),
  };
}
