import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import type { ApiConversation } from "./model";

export function NoteSection({ detail, busy, onSave }: { detail: ApiConversation; busy: boolean; onSave: (note: string) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(detail.note);

  useEffect(() => {
    setEditing(false);
    setDraft(detail.note);
  }, [detail.id, detail.note]);

  return (
    <section className="ctx-section is-note">
      <div className="ctx-section-head">
        <h4>{t("conversations.note")}</h4>
        <button type="button" aria-label={t("conversations.edit_note")} onClick={() => setEditing(true)}><Icon name="edit" size={14} /></button>
      </div>
      {editing ? (
        <div className="ctx-note is-editing">
          <textarea autoFocus disabled={busy} placeholder={t("conversations.internal_note_customer_does_not")} rows={3} value={draft} onChange={(event) => setDraft(event.target.value)} />
          <div className="ctx-note-actions">
            <button type="button" disabled={busy} onClick={() => { setDraft(detail.note); setEditing(false); }}>{t("common.cancel")}</button>
            <button type="button" className="primary" disabled={busy} onClick={() => void onSave(draft).then(() => setEditing(false))}>{t("common.save")}</button>
          </div>
        </div>
      ) : (
        <div className={`ctx-note ${detail.note ? "" : "is-empty"}`} onClick={() => setEditing(true)}>{detail.note || t("conversations.no_notes")}</div>
      )}
    </section>
  );
}
