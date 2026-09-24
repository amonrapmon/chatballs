import { Modal } from "antd";
import { useState } from "react";

import { EmptyState } from "../../shared/ui";
import { Icon } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import { deleteReplyTemplate, type ReplyTemplateRef } from "../conversations/model";
import { fmt, t } from "../../i18n";

// Раздел «Шаблоны ответов» (согласован по образцу кадра N2 «Группы», своего
// кадра в базлайне нет): строка — название · начало текста · дата изменения ·
// изменить/удалить. Создание — primary-кнопкой в шапке раздела, правка —
// окном, как у интеграций. Без права на настройки список только читается.

export function ReplyTemplatesCard({ items, canManage, reload, onEdit }: {
  items: ReplyTemplateRef[];
  canManage: boolean;
  reload: () => void;
  onEdit: (template: ReplyTemplateRef) => void;
}) {
  const [deleting, setDeleting] = useState<ReplyTemplateRef | null>(null);
  const [deleteError, setDeleteError] = useState("");

  async function remove() {
    if (!deleting) return;
    setDeleteError("");
    try {
      await deleteReplyTemplate(deleting.id);
      setDeleting(null);
      reload();
    } catch (caught) {
      setDeleteError(caught instanceof Error ? caught.message : t("settings.could_not_delete"));
    }
  }

  if (items.length === 0) return <EmptyState title={t("settings.no_templates_yet")} />;

  return (
    <>
      <div className="table-card settings-groups-card">
        {items.map((template) => (
          <div
            className={`settings-group-row settings-template-row ${canManage ? "is-clickable" : ""}`}
            key={template.id}
            onClick={canManage ? () => onEdit(template) : undefined}
          >
            <strong>{template.title}</strong>
            <span className="settings-template-preview">{template.text.replace(/\s+/g, " ")}</span>
            <small>{fmt.shortDate(template.updatedAt)}</small>
            {canManage && (
              <div className="settings-group-actions" onClick={(event) => event.stopPropagation()}>
                <button aria-label={t("common.edit")} title={t("common.edit")} type="button" onClick={() => onEdit(template)}><Icon name="edit" size={14} /></button>
                <button aria-label={t("common.delete")} title={t("common.delete")} className="is-danger" type="button" onClick={() => { setDeleteError(""); setDeleting(template); }}><Icon name="trash" size={14} /></button>
              </div>
            )}
          </div>
        ))}
      </div>
      {deleting && (
        <Modal open title={t("settings.delete_template")} onCancel={() => setDeleting(null)} footer={null} destroyOnClose>
          <div className="integration-form">
            <p>{t("settings.template_will_be_deleted", { name: deleting.title })}</p>
            {deleteError && <div className="integration-form-error">{deleteError}</div>}
            <div className="integration-form-actions">
              <Button variant="secondary" onClick={() => setDeleting(null)}>{t("common.cancel")}</Button>
              <Button variant="danger-outline" onClick={() => void remove()}>{t("common.delete")}</Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
