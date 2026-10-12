import { Modal } from "antd";
import { useState } from "react";
import { t } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import { deleteReplyTemplate, type ReplyTemplateRef } from "../conversations/model";

export function TemplateDeleteDialog({ item, onClose, onDeleted }: { item: ReplyTemplateRef; onClose: () => void; onDeleted: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function remove() {
    setBusy(true); setError("");
    try { await deleteReplyTemplate(item.id); onDeleted(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : t("settings.could_not_delete")); }
    finally { setBusy(false); }
  }
  return <Modal open title={t("settings.delete_template")} onCancel={onClose} footer={null}>
    <div className="integration-form"><p>{t("settings.template_will_be_deleted", { name: item.title })}</p>
      {error && <div className="integration-form-error" role="alert">{error}</div>}
      <div className="integration-form-actions"><Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant="danger-outline" disabled={busy} onClick={() => void remove()}>{t("common.delete")}</Button></div></div>
  </Modal>;
}
