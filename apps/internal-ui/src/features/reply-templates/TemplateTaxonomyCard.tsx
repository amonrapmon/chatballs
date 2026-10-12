import { useState } from "react";

import { ApiError } from "../../api/client";
import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import type { ReplyTemplateRef } from "../conversations/model";
import { deleteTaxon, saveTaxon, type TaxonomyKind, type TemplateScope, type TemplateTaxon } from "./api";
import { TemplateTaxonDeleteDialog } from "./TemplateTaxonDeleteDialog";

// Карточка справочника кадра N7: строки с числом шаблонов, переименование в
// строке, создание в подвале. Удаление справочника шаблоны не удаляет.

export function TemplateTaxonomyCard({ kind, scope, items, templates, reload }: {
  kind: TaxonomyKind;
  scope: TemplateScope;
  items: TemplateTaxon[];
  templates: ReplyTemplateRef[];
  reload: () => void;
}) {
  const isCategory = kind === "categories";
  const [editing, setEditing] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [newName, setNewName] = useState("");
  const [deleting, setDeleting] = useState<TemplateTaxon | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ target: number | "new"; text: string } | null>(null);
  const count = (id: number) => templates.filter((item) => (isCategory ? item.categoryId === id : item.tagIds.includes(id))).length;
  const mark = isCategory ? "" : "# ";

  async function save(target: number | "new", value: string) {
    if (busy || !value.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await saveTaxon(kind, scope, value.trim(), target === "new" ? undefined : target);
      setEditing(null);
      setNewName("");
      reload();
    } catch (caught) {
      const text = caught instanceof ApiError && caught.status === 409
        ? t(isCategory ? "templates.duplicate_category" : "templates.duplicate_tag")
        : caught instanceof Error ? caught.message : t("common.could_not_complete_action");
      setError({ target, text });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="table-card template-taxonomy-card">
      <h3>{t(isCategory ? "templates.categories" : "templates.tags")}</h3>
      <div className="template-taxonomy-row template-library-head">
        <span>{t(isCategory ? "common.title" : "templates.tag")}</span>
        <span>{t("templates.taxonomy_count")}</span>
        <span />
      </div>
      {items.map((item) => editing === item.id ? (
        <div className="template-taxonomy-row is-editing" key={item.id}>
          <div className="template-taxonomy-edit">
            <input
              aria-label={t("common.title")}
              aria-invalid={error?.target === item.id}
              autoFocus
              value={name}
              onChange={(event) => { setName(event.target.value); setError(null); }}
              onKeyDown={(event) => {
                if (event.key === "Enter") void save(item.id, name);
                if (event.key === "Escape") setEditing(null);
              }}
            />
            {error?.target === item.id && <small className="form-field-error" role="alert">{error.text}</small>}
          </div>
          <span className="template-taxonomy-count">{fmt.number(count(item.id))}</span>
          <div className="template-taxonomy-actions">
            <Button variant="secondary" onClick={() => { setEditing(null); setError(null); }}>{t("common.cancel")}</Button>
            <Button variant="primary" disabled={busy || !name.trim()} onClick={() => void save(item.id, name)}>{t("common.save")}</Button>
          </div>
        </div>
      ) : (
        <div className={`template-taxonomy-row ${deleting?.id === item.id ? "is-deleting" : ""}`.trim()} key={item.id}>
          <strong>{mark}{item.name}</strong>
          <span className="template-taxonomy-count">{fmt.number(count(item.id))}</span>
          <div className="settings-group-actions">
            <button aria-label={t("templates.rename")} title={t("templates.rename")} type="button" disabled={busy} onClick={() => { setEditing(item.id); setName(item.name); setError(null); }}><Icon name="edit" size={14} /></button>
            <button aria-label={t("common.delete")} title={t("common.delete")} className="is-danger" type="button" disabled={busy} onClick={() => setDeleting(item)}><Icon name="trash" size={14} /></button>
          </div>
        </div>
      ))}
      <div className="template-taxonomy-add">
        <input
          aria-label={t(isCategory ? "templates.new_category" : "templates.new_tag")}
          aria-invalid={error?.target === "new"}
          placeholder={t(isCategory ? "templates.new_category" : "templates.new_tag")}
          value={newName}
          onChange={(event) => { setNewName(event.target.value); setError(null); }}
          onKeyDown={(event) => { if (event.key === "Enter") void save("new", newName); }}
        />
        <Button variant="secondary" icon="plus" iconSize={14} disabled={busy || !newName.trim()} onClick={() => void save("new", newName)}>{t("templates.create_taxon")}</Button>
      </div>
      {error?.target === "new" && <small className="form-field-error template-taxonomy-error" role="alert">{error.text}</small>}
      {isCategory && <p className="template-library-note">{t("templates.one_category")}</p>}
      {deleting && (
        <TemplateTaxonDeleteDialog
          kind={kind}
          name={deleting.name}
          count={count(deleting.id)}
          onClose={() => setDeleting(null)}
          onDelete={() => deleteTaxon(kind, deleting.id)}
          onDeleted={() => { setDeleting(null); reload(); }}
        />
      )}
    </section>
  );
}
