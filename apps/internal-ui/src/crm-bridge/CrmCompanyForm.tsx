import { useState } from "react";

import { t } from "../i18n";
import { Button } from "../shared/ui-controls";
import type { CrmCompany } from "./model";

export function CrmCompanyForm({ company, disabled, onSave, onRemove, onCancel }: {
  company?: CrmCompany;
  disabled: boolean;
  onSave: (name: string, externalId: string, isActive: boolean) => void;
  onRemove?: () => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(company?.name ?? "");
  const [externalId, setExternalId] = useState(company?.externalCompanyId ?? "");
  const [isActive, setIsActive] = useState(company?.isActive ?? true);
  const valid = name.trim() !== "" && /^[0-9]{1,40}$/.test(externalId);
  return (
    <form className="crm-company-form" onSubmit={(event) => {
      event.preventDefault();
      if (valid) onSave(name.trim(), externalId, isActive);
    }}>
      <div className="crm-field-grid">
        <label>{t("crm.company_name")}
          <input maxLength={160} value={name} disabled={disabled}
            onChange={(event) => setName(event.target.value)} />
        </label>
        <label>{t("crm.company_id")}
          <input maxLength={40} inputMode="numeric" value={externalId} disabled={disabled}
            onChange={(event) => setExternalId(event.target.value)} />
        </label>
      </div>
      <p className="crm-section-note">{t("crm.id_hint")}</p>
      {company && !company.isPrimary && (
        <label className="crm-status-toggle">
          <input type="checkbox" checked={isActive} disabled={disabled}
            onChange={(event) => setIsActive(event.target.checked)} />
          {t("crm.active")}
        </label>
      )}
      <div className="crm-form-actions">
        {onRemove && (
          <Button variant="danger-outline" disabled={disabled} onClick={onRemove}>
            {t("crm.remove_company")}
          </Button>
        )}
        <button type="button" className="link is-muted" disabled={disabled} onClick={onCancel}>
          {t("common.cancel")}
        </button>
        <Button type="submit" variant="primary" disabled={disabled || !valid}>
          {t("crm.save_company")}
        </Button>
      </div>
    </form>
  );
}
