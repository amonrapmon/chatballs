import type { PreparedContent } from "@chatballs/ui";
import { api, ApiError } from "../../../api/client";
import { t } from "../../../i18n";
import type { Configuration } from "../model";

export type Diagnostic = { origin: string; tab: string; path: string; detail: string; reference?: string; line?: number; column?: number };
export const isParentError = (error: Diagnostic) => error.origin === "configuration"
  && ["name", "description", "instruction"].includes(error.path);
export const validateDraft = (configuration: Configuration, signal?: AbortSignal) =>
  api<{ valid: true }>("/api/v1/skills/validate/", { method: "POST", body: JSON.stringify({ configuration }), signal });
export const previewDraft = (configuration: Configuration, templateId: string, data: unknown, signal?: AbortSignal) =>
  api<PreparedContent>("/api/v1/skills/preview/", {
    method: "POST", body: JSON.stringify({ configuration, templateId, data }), signal,
  });
export function diagnostics(caught: unknown): Diagnostic[] {
  if (!(caught instanceof ApiError)) return [];
  const errors = caught.payload.errors;
  if (!Array.isArray(errors)) return [];
  return errors.map((error) => ({ ...error,
    origin: error.origin ?? "configuration", tab: error.tab ?? "schema", path: error.path ?? "",
    line: error.line === undefined ? undefined : Number(error.line),
    column: error.column === undefined ? undefined : Number(error.column),
  }));
}
export const exampleError = (): Diagnostic => ({ origin: "example", tab: "example", path: "", detail: t("skill_templates.invalid_json") });
export const forTemplate = (errors: Diagnostic[], index: number) => errors
  .filter((error) => error.origin === "example" || error.path === `templates[${index}]` || error.path.startsWith(`templates[${index}].`))
  .map((error) => ({ ...error, path: error.path.replace(new RegExp(`^templates\\[${index}\\]\\.?`), "") }));

/** API container paths are implementation detail, not product copy. */
export function displayDiagnostics(errors: Diagnostic[], configuration: Configuration, current: number) {
  return errors.map((error) => {
    const match = /^templates\[(\d+)\]\.?/.exec(error.path);
    let path = match ? error.path.slice(match[0].length) : error.path;
    if (error.origin !== "example") {
      if (path === "name") path = t("skills.name");
      if (path === "purpose") path = t("skill_templates.purpose");
      if (path === "exampleNames") path = t("skill_templates.example");
    }
    if (match && Number(match[1]) !== current) {
      const template = configuration.templates[Number(match[1])];
      path = [template?.name || t("skill_templates.new"), path].filter(Boolean).join(": ");
    }
    return { ...error, path };
  });
}
