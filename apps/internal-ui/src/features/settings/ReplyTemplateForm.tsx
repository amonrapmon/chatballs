import { Modal } from "antd";
import { useRef, useState } from "react";

import { FormField, TextAreaField } from "../../shared/form-controls";
import { Button } from "../../shared/ui-controls";
import { createReplyTemplate, updateReplyTemplate, type ReplyTemplateRef } from "../conversations/model";
import { variableToken, type TemplateVariable } from "../conversations/templateVariables";
import { TemplateVariableMenu } from "./TemplateVariableMenu";
import { t } from "../../i18n";

// Окно шаблона ответа: название и текст. Та же форма, что у интеграций и
// переименования группы; ошибки (занятое название, пустой текст) — от сервера.

export function ReplyTemplateForm({ initial, onClose, onSaved }: {
  initial: ReplyTemplateRef | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [text, setText] = useState(initial?.text ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const textRef = useRef<HTMLTextAreaElement>(null);

  function insertVariable(variable: TemplateVariable) {
    const token = variableToken(variable);
    const area = textRef.current;
    const start = area?.selectionStart ?? text.length;
    const end = area?.selectionEnd ?? text.length;
    setText(text.slice(0, start) + token + text.slice(end));
    window.requestAnimationFrame(() => {
      if (!area) return;
      area.focus();
      area.setSelectionRange(start + token.length, start + token.length);
    });
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      if (initial) await updateReplyTemplate(initial.id, title.trim(), text.trim());
      else await createReplyTemplate(title.trim(), text.trim());
      onSaved();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("settings.could_not_save_template"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open title={initial ? t("settings.edit_template") : t("settings.new_template")} onCancel={onClose} footer={null} destroyOnClose>
      <div className="integration-form">
        <FormField label={t("common.title")} value={title} onChange={setTitle} />
        <TextAreaField label={t("settings.template_text")} value={text} onChange={setText} inputRef={textRef} />
        <TemplateVariableMenu onPick={insertVariable} />
        {error && <div className="integration-form-error">{error}</div>}
        <div className="integration-form-actions">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button variant="primary" disabled={saving || !title.trim() || !text.trim()} onClick={() => void save()}>{t("common.save")}</Button>
        </div>
      </div>
    </Modal>
  );
}
