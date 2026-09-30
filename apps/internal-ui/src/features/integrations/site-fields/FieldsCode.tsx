import { t } from "../../../i18n";
import { CopyButton } from "../../../shared/ui-controls";
import { fieldsSnippet, type SiteField } from "./model";

export function FieldsCode({ fields }: { fields: SiteField[] }) {
  const snippet = fieldsSnippet(fields);
  return <div className="site-fields-card site-fields-code">
    <div className="site-fields-card-head"><div><strong>{t("site_fields.code_title")}</strong><small>{t("site_fields.code_hint")}</small></div>
      <CopyButton value={snippet} label={t("common.copy")} className="secondary-button" />
    </div><pre>{snippet}</pre>
  </div>;
}
