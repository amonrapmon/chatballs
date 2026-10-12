import { Modal } from "antd";
import { useState } from "react";

import { t, tn } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import type { TaxonomyKind } from "./api";

// Окно кадра N7: удаление категории или тега оставляет шаблоны в библиотеке.

export function TemplateTaxonDeleteDialog({ kind, name, count, onClose, onDelete, onDeleted }: {
  kind: TaxonomyKind;
  name: string;
  count: number;
  onClose: () => void;
  onDelete: () => Promise<unknown>;
  onDeleted: () => void;
}) {
  const isCategory = kind === "categories";
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await onDelete();
      onDeleted();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("settings.could_not_delete"));
      setBusy(false);
    }
  }

  return (
    <Modal open width={460} title={t(isCategory ? "templates.delete_category" : "templates.delete_tag", { name })} onCancel={onClose} footer={null} destroyOnHidden>
      <div className="integration-form">
        <p>{tn(isCategory ? "templates.category_keeps_templates" : "templates.tag_keeps_templates", count)}</p>
        {error && <div className="integration-form-error" role="alert">{error}</div>}
        <div className="integration-form-actions">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button variant="danger-outline" disabled={busy} onClick={() => void remove()}>{t(isCategory ? "templates.delete_category_action" : "templates.delete_tag_action")}</Button>
        </div>
      </div>
    </Modal>
  );
}
