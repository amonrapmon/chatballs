import { useEffect, useState } from "react";
import { t } from "../../../i18n";
import { Button } from "../../../shared/ui-controls";
import type { Integration } from "../model";
import { ContactFieldsTable } from "./ContactFieldsTable";
import { CustomFieldsTable } from "./CustomFieldsTable";
import { FieldDialog } from "./FieldDialog";
import { FieldsCode } from "./FieldsCode";
import { OptionDialog } from "./OptionDialog";
import type { FieldOption, SiteField } from "./model";
import { useSiteFields } from "./useSiteFields";
import "./styles.css";

type Editing = { kind: "field"; field?: SiteField } | { kind: "option"; key: string; index?: number };

export function SiteFieldsSection({ integration, onSaved, onCount }: {
  integration: Integration;
  onSaved: (integration: Integration) => void;
  onCount: (count: number) => void;
}) {
  const { fields, change, save, busy, error, dirty } = useSiteFields(integration, onSaved);
  const [editing, setEditing] = useState<Editing>();
  useEffect(() => onCount(fields.length), [fields.length, onCount]);
  const optionField = editing?.kind === "option" ? fields.find((field) => field.key === editing.key) : undefined;
  function confirmField(field: SiteField) {
    change(editing?.kind === "field" && editing.field
      ? fields.map((item) => item.key === field.key ? field : item) : [...fields, field]);
    setEditing(undefined);
  }
  function confirmOption(option?: FieldOption) {
    if (editing?.kind !== "option" || !optionField) return;
    const options = [...(optionField.options ?? [])];
    if (editing.index === undefined && option) options.push(option);
    else if (editing.index !== undefined) options.splice(editing.index, 1, ...(option ? [option] : []));
    change(fields.map((field) => field.key === optionField.key ? { ...field, options } : field));
    setEditing(undefined);
  }
  return <div className="site-fields-section">
    <div className="portal-settings-heading"><h3>{t("settings.site_data")}</h3><p>{t("site_fields.description")}</p></div>
    <ContactFieldsTable />
    <CustomFieldsTable fields={fields} busy={busy} onChange={change} onAdd={() => setEditing({ kind: "field" })}
      onRename={(field) => setEditing({ kind: "field", field })}
      onOption={(key, index) => setEditing({ kind: "option", key, index })} />
    <FieldsCode fields={fields} />
    {error && <div className="integration-form-error" role="alert">{error}</div>}
    <div className="portal-settings-actions"><Button variant="primary" disabled={busy || !dirty} onClick={() => void save()}>
      {busy ? t("ai.saving") : t("common.save")}
    </Button></div>
    {editing?.kind === "field" && <FieldDialog initial={editing.field} fields={fields} onClose={() => setEditing(undefined)} onConfirm={confirmField} />}
    {editing?.kind === "option" && optionField && <OptionDialog options={optionField.options ?? []} index={editing.index}
      onClose={() => setEditing(undefined)} onConfirm={confirmOption} onDelete={() => confirmOption()} />}
  </div>;
}
