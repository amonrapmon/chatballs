import { t } from "../../../i18n";
import { BackLink, Button } from "../../../shared/ui-controls";
import { EmptyState } from "../../../shared/ui";
import type { useSkillDraft } from "../useSkillDraft";
import { configurationOf, emptyConfiguration, validateConfiguration } from "../model";
import { displayDiagnostics, forTemplate, isParentError } from "./api";
import { changesOutside, updateTemplate, withExamples } from "./model";
import { TemplateFields } from "./TemplateFields";
import { TemplateCode } from "./TemplateCode";
import { TemplateExamples } from "./TemplateExamples";
import { TemplatePreview } from "./TemplatePreview";
import { useTemplatePreview } from "./useTemplatePreview";
import { orderedExample } from "./schemaOrder";
import type { SchemaNode } from "./schema";
import "./layout.css";
import "./code.css";
import "./preview.css";

export function TemplateEditor({ state, templateId, back, library, parentErrors, refresh }: {
  state: ReturnType<typeof useSkillDraft>; templateId: string; back: () => void;
  parentErrors: () => void; refresh: () => void; library: () => void;
}) {
  const { draft, setDraft, saved, busy, conflict, error, save, exampleInputs, setExampleInputs } = state;
  const selected = state.exampleSelections[templateId] ?? 0;
  const select = (index: number) => state.selectExample(templateId, index);
  const touched = state.templateTouches[templateId] ?? {};
  const touch = (path: string) => state.touchTemplate(templateId, [path]);
  const index = draft.templates.findIndex((template) => template.id === templateId);
  const template = draft.templates[index];
  const schema = (template?.schema ?? { type: "object", properties: {} }) as SchemaNode;
  const inputs = exampleInputs[templateId] ?? (template?.examples.length ? template.examples : [{}])
    .map((item) => JSON.stringify(orderedExample(item, schema), null, 2));
  const preview = useTemplatePreview(draft, templateId, inputs[selected] ?? "{}");
  const visibleErrors = preview.errors.filter((item) => {
    if (state.attempted) return true;
    const local = forTemplate([item], index)[0];
    if (!local) return false;
    return touched[local.path] || touched[local.tab] || (touched.schema && !["name", "purpose"].includes(local.path));
  });
  const errors = forTemplate(visibleErrors, index);
  const change = (next: typeof template) => {
    const fields = Object.keys(next).filter((key) => next[key as keyof typeof next] !== template[key as keyof typeof template]);
    state.touchTemplate(templateId, fields.map((key) => key === "examples" ? "example" : key));
    setDraft(updateTemplate(draft, next));
  };
  async function saveTemplate() {
    if (!(await save()) && state.parentInvalid()) parentErrors();
  }
  if (!template) return <div className="template-editor"><BackLink label={t("skills.skill")} onClick={back} />
    <EmptyState title={t("skill_templates.not_found")} /></div>;
  const outside = changesOutside(draft, saved ? configurationOf(saved) : emptyConfiguration(), templateId);
  return <div className="template-editor">
    <div className="template-breadcrumb"><BackLink label={t("skills.title")} onClick={library} /><span>›</span>
      <button className="link is-muted" onClick={back}>{draft.name}</button><span>›</span><strong>{t("skill_templates.template")}</strong></div>
    <header className="template-header"><div><h2>{template.name || t("skill_templates.new")}
      {state.dirty && <b className="skill-dirty-badge">{t("skill_templates.unsaved")}</b>}</h2><p>{t("skill_templates.history")}</p></div>
      <div><div className="skill-actions"><Button variant="secondary" disabled={busy} onClick={back}>{t("common.cancel")}</Button>
        <Button variant="primary" disabled={busy || conflict || (preview.pending && !Object.keys(validateConfiguration(draft)).length)
          || preview.errors.some((item) => item.origin === "configuration" && !isParentError(item))}
          onClick={() => void saveTemplate()}>{t("skill_templates.save")}</Button></div>
        {outside && <small>{t("skill_templates.saved_together")}</small>}</div>
    </header>
    {error && <div className="skill-notice is-error" role="alert"><span>{error}</span>
      <Button variant="secondary" disabled={busy} onClick={conflict ? refresh : () => void saveTemplate()}>{t(conflict ? "skills.refresh" : "common.try_again")}</Button></div>}
    <div className="template-editor-grid">
      <TemplateFields template={template} change={change} errors={errors} disabled={busy} touch={touch} />
      <TemplateCode template={template} change={change} errors={errors} disabled={busy} updatedAt={saved?.updatedAt} />
      <div className="template-right"><TemplateExamples template={template} inputs={inputs} selected={selected} select={select}
        errors={errors.filter((item) => item.tab === "example")} disabled={busy} change={(next) => {
          setExampleInputs({ ...exampleInputs, [templateId]: next }); change(withExamples(template, next));
        }} />
        <TemplatePreview content={preview.content} errors={displayDiagnostics(visibleErrors, draft, index)} failure={preview.failure} retry={preview.retry} />
      </div>
    </div>
  </div>;
}
