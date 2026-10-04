import { t } from "../../../i18n";
import { Icon } from "../../../shared/icons";
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
      <thead><tr>{(["key", "label", "type", "target", "ai_access"] as const).map((key) => <th key={key}>{t(`site_fields.${key}`)}</th>)}</tr></thead>
      <tbody>{contacts.map((field) => <tr key={field.key}>
        <td><code>{field.key}</code></td><td>{t(field.label)}</td>
        <td><span className="site-field-type"><FieldTypeIcon type={field.type} />{t(`site_fields.${field.type}`)}</span></td>
        <td>{t(field.target)}</td>
        <td><span className="site-field-type" title={t("site_fields.ai_masked_hint")}><Icon name="mask" size={13} strokeWidth={1.9} />{t("site_fields.ai_masked")}</span></td>
      </tr>)}</tbody>
    </table>
  </div>;
}
