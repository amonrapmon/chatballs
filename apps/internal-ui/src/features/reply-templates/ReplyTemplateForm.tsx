import { Modal } from "antd";
import { useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { t, tn } from "../../i18n";
import { FormField, SelectField } from "../../shared/form-controls";
import { Button } from "../../shared/ui-controls";
import type { ReplyTemplateRef } from "../conversations/model";
import { TEMPLATE_TOKEN } from "../conversations/templateVariables";
import { saveTemplate, templateTaxonomy, templateVariables, type TemplateScope, type TemplateTaxon, type TemplateVariable } from "./api";
import { TemplateScopeTabs } from "./TemplateScopeTabs";
import { TemplateTagPicker } from "./TemplateTagPicker";
import { TemplateVariableMenu } from "./TemplateVariableMenu";
import { TokenEditor, type TokenEditorHandle } from "./TokenEditor";
import "./form.css";

// Окно шаблона (кадры N5, N6, N9): название, область, одна категория,
// несколько тегов и текст с переменными серверного каталога. Область
// существующего шаблона не меняется — так устроен контракт API.

export function ReplyTemplateForm({ initial, initialScope, canManageShared, onClose, onSaved }: {
  initial: ReplyTemplateRef | null;
  initialScope: TemplateScope;
  canManageShared: boolean;
  onClose: () => void;
  /** Область сохранённого шаблона: библиотека открывает её вкладку. */
  onSaved: (scope: TemplateScope) => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [text, setText] = useState(initial?.text ?? "");
  const [scope, setScope] = useState<TemplateScope>(initial?.scope ?? initialScope);
  const [categoryId, setCategoryId] = useState<number | null>(initial?.categoryId ?? null);
  const [tagIds, setTagIds] = useState(initial?.tagIds ?? []);
  const [categories, setCategories] = useState<TemplateTaxon[]>([]);
  const [tags, setTags] = useState<TemplateTaxon[]>([]);
  const [variables, setVariables] = useState<TemplateVariable[]>([]);
  const [ready, setReady] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [titleError, setTitleError] = useState("");
  const [unknownKeys, setUnknownKeys] = useState<string[]>([]);
  const editorRef = useRef<TokenEditorHandle>(null);

  useEffect(() => {
    let active = true;
    Promise.all([templateTaxonomy("categories"), templateTaxonomy("tags"), templateVariables()])
      .then(([cats, labels, catalog]) => {
        if (!active) return;
        setCategories(cats);
        setTags(labels);
        setVariables(catalog);
        setReady(true);
      })
      .catch(() => { if (active) setError(t("settings.could_not_load_templates")); });
    return () => { active = false; };
  }, []);

  // Текст старого шаблона не отправляется повторно, пока его не трогали:
  // удалённое дополнительное поле не мешает переименовать шаблон.
  const textChanged = !initial || text !== initial.text;
  const unknownIn = (catalog: TemplateVariable[]) => [...new Set([...text.matchAll(TEMPLATE_TOKEN)].map((match) => match[1].trim()))]
    .filter((key) => !catalog.some((item) => item.key === key));

  async function save() {
    setError("");
    if (textChanged && unknownIn(variables).length > 0) {
      setUnknownKeys(unknownIn(variables));
      return;
    }
    setSaving(true);
    try {
      await saveTemplate(initial?.id, { title: title.trim(), ...(textChanged ? { text: text.trim() } : {}), scope, categoryId, tagIds });
      onSaved(scope);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        setTitleError(t(scope === "SHARED" ? "templates.duplicate_shared" : "templates.duplicate_personal"));
      } else if (caught instanceof ApiError && caught.status === 400 && textChanged) {
        // Каталог мог измениться, пока окно было открыто: сверяемся заново.
        const catalog = await templateVariables().catch(() => variables);
        setVariables(catalog);
        if (unknownIn(catalog).length > 0) setUnknownKeys(unknownIn(catalog));
        else setError(caught.message || t("settings.could_not_save_template"));
      } else {
        setError(caught instanceof Error ? caught.message : t("settings.could_not_save_template"));
      }
    } finally {
      setSaving(false);
    }
  }

  const errorCount = (titleError ? 1 : 0) + (unknownKeys.length > 0 ? 1 : 0);
  return (
    <Modal open width={620} title={t(initial ? "settings.edit_template" : "settings.new_template")} onCancel={onClose} footer={null} destroyOnHidden>
      <div className="integration-form template-form">
        <div className="template-form-grid">
          <FormField wide label={t("common.title")} value={title} error={titleError} onChange={(value) => { setTitle(value); setTitleError(""); }} />
          <div className="readonly-field">
            <span>{t("templates.scope")}</span>
            <TemplateScopeTabs
              value={scope}
              singular
              disabled={Boolean(initial)}
              sharedLocked={!canManageShared}
              onChange={(value) => { if (value && value !== scope) { setScope(value); setCategoryId(null); setTagIds([]); } }}
            />
            <small className="template-form-help">{t(canManageShared ? "templates.shared_help" : "templates.permission_help")}</small>
          </div>
          <SelectField
            label={t("templates.category")}
            value={categoryId ? String(categoryId) : ""}
            options={[["", t("templates.no_category")], ...categories.filter((item) => item.scope === scope).map((item): [string, string] => [String(item.id), item.name])]}
            onChange={(value) => setCategoryId(value ? Number(value) : null)}
          />
          <TemplateTagPicker tags={tags.filter((item) => item.scope === scope)} value={tagIds} onChange={setTagIds} />
          <div className="readonly-field wide">
            <span className="template-text-label">
              {t("settings.template_text")}
              <TemplateVariableMenu variables={variables} onPick={(variable) => editorRef.current?.insert(variable.token)} />
            </span>
            <TokenEditor
              className="template-form-editor"
              editorRef={editorRef}
              label={t("settings.template_text")}
              value={text}
              variables={variables}
              invalidKeys={unknownKeys}
              onChange={(value) => { setText(value); setUnknownKeys([]); }}
            />
            {unknownKeys.length > 0
              ? <small className="form-field-error" role="alert">{tn("templates.unknown_variables", unknownKeys.length, { names: unknownKeys.join("», «"), available: variables.map((item) => item.label).join(", ") })}</small>
              : <small className="template-form-help">{t("templates.variable_help")}</small>}
          </div>
        </div>
        {error && <div className="integration-form-error" role="alert">{error}</div>}
        <div className="integration-form-actions">
          <small className="template-form-footnote">{errorCount > 0 && tn("templates.fix_errors", errorCount)}</small>
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button variant="primary" disabled={!ready || saving || !title.trim() || !text.trim()} onClick={() => void save()}>{t("common.save")}</Button>
        </div>
      </div>
    </Modal>
  );
}
