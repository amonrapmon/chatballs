import { ColorPicker, Modal, theme } from "antd";
import { useState } from "react";
import { t } from "../../../i18n";
import { FormField } from "../../../shared/form-controls";
import { Button } from "../../../shared/ui-controls";
import { optionError, type FieldOption } from "./model";

export function OptionDialog({ options, index, onClose, onConfirm, onDelete }: {
  options: FieldOption[];
  index?: number;
  onClose: () => void;
  onConfirm: (option: FieldOption) => void;
  onDelete: () => void;
}) {
  const [option, setOption] = useState<FieldOption>(index === undefined ? { label: "", value: "" } : options[index]);
  const [error, setError] = useState<string>();
  const { token } = theme.useToken();
  function confirm() {
    const next = { ...option, label: option.label.trim(), value: option.value.trim() };
    const invalid = optionError(next, options, index);
    if (invalid) { setError(invalid); return; }
    onConfirm(next);
  }
  return <Modal open title={t("site_fields.option_title")} onCancel={onClose} footer={null}>
    <form className="integration-form" onSubmit={(event) => { event.preventDefault(); confirm(); }}>
      <FormField label={t("site_fields.label")} value={option.label} onChange={(label) => setOption({ ...option, label })} />
      <FormField label={t("site_fields.value")} mono value={option.value} onChange={(value) => setOption({ ...option, value })} />
      <div className="site-field-color">
        <FormField label={t("site_fields.color")} mono value={option.color ?? ""} onChange={(color) => setOption({ ...option, color })} />
        <ColorPicker value={option.color || token.colorPrimary} disabledAlpha onChangeComplete={(color) => setOption({ ...option, color: color.toHexString() })} />
      </div>
      {error && <div className="integration-form-error" role="alert">{error}</div>}
      <div className="integration-form-actions">
        {index !== undefined && <Button variant="danger-outline" onClick={onDelete}>{t("common.delete")}</Button>}
        <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant="primary" type="submit">{t("common.save")}</Button>
      </div>
    </form>
  </Modal>;
}
