import { Modal } from "antd";
import { useState } from "react";
import { t } from "../../../i18n";
import { FormField, SelectField } from "../../../shared/form-controls";
import { Button } from "../../../shared/ui-controls";
import { fieldError, fieldTypeOptions, type FieldType, type SiteField } from "./model";

export function FieldDialog({ initial, fields, onClose, onConfirm }: {
  initial?: SiteField;
  fields: SiteField[];
  onClose: () => void;
  onConfirm: (field: SiteField) => void;
}) {
  const [field, setField] = useState<SiteField>(initial ?? {
    key: "", label: "", type: "string", aiVisible: false, order: fields.length,
  });
  const [error, setError] = useState<string>();
  function confirm() {
    const next = { ...field, key: field.key.trim(), label: field.label.trim(),
      ...(field.type === "enum" ? { options: field.options ?? [] } : {}) };
    const invalid = fieldError(next, fields, !initial);
    if (invalid) { setError(invalid); return; }
    onConfirm(next);
  }
  return <Modal open title={t(initial ? "site_fields.rename" : "site_fields.add")} onCancel={onClose} footer={null}>
    <form className="integration-form" onSubmit={(event) => { event.preventDefault(); confirm(); }}>
      <FormField label={t("site_fields.key")} mono value={field.key}
        onChange={initial ? undefined : (key) => setField({ ...field, key })} />
      {!initial && <small className="integration-form-hint">{t("site_fields.key_hint")}</small>}
      <FormField label={t("site_fields.label")} value={field.label} onChange={(label) => setField({ ...field, label })} />
      {!initial && <SelectField label={t("site_fields.type")} value={field.type} options={fieldTypeOptions}
        onChange={(type) => setField({ ...field, type: type as FieldType })} />}
      {error && <div className="integration-form-error" role="alert">{error}</div>}
      <div className="integration-form-actions">
        <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant="primary" type="submit">{t("common.save")}</Button>
      </div>
    </form>
  </Modal>;
}
