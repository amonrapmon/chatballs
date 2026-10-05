import { t } from "../../../i18n";
import { FieldTypeIcon } from "./FieldTypeIcon";

const contacts = [
  { key: "name", type: "string", label: "common.name", target: "site_fields.target_name" },
  { key: "email", type: "email", label: "site_fields.email", target: "site_fields.target_email" },
  { key: "phone", type: "phone", label: "site_fields.phone", target: "site_fields.target_phone" },
] as const;

export function ContactFieldsTable() {
  return <div className="site-fields-card">
    <div className="site-fields-card-head"><div>
      <strong>{t("site_fields.contacts")}</strong><small>{t("site_fields.contacts_hint")}</small>
    </div></div>
    <table className="site-fields-table site-fields-contacts">
      <thead><tr>{["key", "label", "type", "target"].map((key) => <th key={key}>{t(`site_fields.${key as "key" | "label" | "type" | "target"}`)}</th>)}</tr></thead>
      <tbody>{contacts.map((field) => <tr key={field.key}>
        <td><code>{field.key}</code></td><td>{t(field.label)}</td>
        <td><span className="site-field-type"><FieldTypeIcon type={field.type} />{t(`site_fields.${field.type}`)}</span></td>
        <td>{t(field.target)}</td>
      </tr>)}</tbody>
    </table>
  </div>;
}
