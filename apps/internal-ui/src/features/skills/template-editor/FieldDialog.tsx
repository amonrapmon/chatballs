import { Modal } from "antd";
import { useState } from "react";
import { t } from "../../../i18n";
import { FormField, SelectField, SwitchButton, TextAreaField } from "../../../shared/form-controls";
import { Button } from "../../../shared/ui-controls";
import { applyField, fieldDraft, parentOptions, typeOptions, type FieldType, type SchemaNode } from "./schema";

export function FieldDialog({ schema, editing, close, change }: {
  schema: SchemaNode; editing?: string; close: () => void; change: (schema: SchemaNode) => void;
}) {
  const [draft, setDraft] = useState(() => fieldDraft(schema, editing));
  const [error, setError] = useState("");
  function confirm() {
    try { change(applyField(schema, draft, editing)); close(); }
    catch (caught) { setError((caught as Error).message); }
  }
  function changeType(index: number, type: FieldType) {
    const types = [...draft.types.slice(0, index), type];
    if (type === "list") types.push("string");
    setDraft({ ...draft, types });
  }
  return <Modal open title={t(editing ? "skill_templates.edit_field" : "skill_templates.add_field")}
    onCancel={close} footer={null}>
    <form className="integration-form" onSubmit={(event) => { event.preventDefault(); confirm(); }}>
      <FormField label={t("skill_templates.field_name")} mono value={draft.name}
        onChange={(name) => setDraft({ ...draft, name })} />
      <TextAreaField label={t("skill_templates.description")} value={draft.description}
        onChange={(description) => setDraft({ ...draft, description })} />
      {draft.types.map((type, index) => <SelectField key={index}
        label={t(index ? "skill_templates.item_type" : "skill_templates.type")} value={type}
        options={typeOptions()} onChange={(value) => changeType(index, value as FieldType)} />)}
      <div className="template-required"><span>{t("skill_templates.required")}</span>
        <SwitchButton className="ui-switch is-compact" label={t("skill_templates.required")} checked={draft.required}
          onClick={() => setDraft({ ...draft, required: !draft.required })} /></div>
      <SelectField label={t("skill_templates.parent")} value={draft.parent} options={parentOptions(schema, editing)}
        onChange={(parent) => setDraft({ ...draft, parent })} />
      {error && <div className="integration-form-error" role="alert">{error}</div>}
      <div className="integration-form-actions">
        <Button variant="secondary" onClick={close}>{t("common.cancel")}</Button>
        <Button variant="primary" type="submit">{t("common.save")}</Button>
      </div>
    </form>
  </Modal>;
}
