import { useRef } from "react";
import { fmt, t } from "../../../i18n";
import { Button } from "../../../shared/ui-controls";
import { CustomFieldRow } from "./CustomFieldRow";
import { moveField, type SiteField } from "./model";

export function CustomFieldsTable({ fields, busy, onChange, onAdd, onRename, onOption }: {
  fields: SiteField[];
  busy: boolean;
  onChange: (fields: SiteField[]) => void;
  onAdd: () => void;
  onRename: (field: SiteField) => void;
  onOption: (key: string, index?: number) => void;
}) {
  const dragged = useRef<string | undefined>(undefined);
  return <div className="site-fields-card">
    <div className="site-fields-card-head"><div>
      <strong>{t("site_fields.custom")}</strong><small>{t("site_fields.count", { count: fmt.number(fields.length) })}</small>
    </div><Button variant="primary" icon="plus" disabled={busy || fields.length >= 30} onClick={onAdd}>{t("site_fields.add")}</Button></div>
    <table className="site-fields-table site-fields-custom">
      <thead><tr><th /><th>{t("site_fields.key")}</th><th>{t("site_fields.label")}</th>
        <th>{t("site_fields.type")}</th><th>{t("site_fields.ai")}</th><th /></tr></thead>
      <tbody>{fields.map((field, index) => <CustomFieldRow key={field.key} field={field} disabled={busy}
        onChange={(updated) => onChange(fields.map((item) => item.key === field.key ? updated : item))}
        onRename={() => onRename(field)} onDelete={() => onChange(fields.filter((item) => item.key !== field.key))}
        onOption={(optionIndex) => onOption(field.key, optionIndex)}
        onDrag={() => { dragged.current = field.key; }} onDragEnd={() => { dragged.current = undefined; }}
        onDrop={() => { if (dragged.current) onChange(moveField(fields, dragged.current, field.key)); dragged.current = undefined; }}
        onMove={(direction) => { const target = fields[index + direction]; if (target) onChange(moveField(fields, field.key, target.key)); }}
      />)}</tbody>
    </table>
    <div className="site-fields-footer">{t("site_fields.types_hint")}</div>
  </div>;
}
