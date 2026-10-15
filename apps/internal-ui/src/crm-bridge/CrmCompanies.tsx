import { useState } from "react";

import { t } from "../i18n";
import type { CrmCompany } from "./model";
import { CrmCompanyForm } from "./CrmCompanyForm";

type Changes = Partial<{ name: string; externalCompanyId: string; isPrimary: boolean; isActive: boolean }>;

export function CrmCompanies({ companies, disabled, onCreate, onUpdate, onRemove }: {
  companies: CrmCompany[]; disabled: boolean;
  onCreate: (name: string, externalId: string) => void;
  onUpdate: (id: number, changes: Changes) => void;
  onRemove: (id: number) => void;
}) {
  const [editing, setEditing] = useState<number | "new" | null>(null);
  const primary = companies.find((item) => item.isPrimary);
  const other = companies.filter((item) => item.id !== primary?.id);
  const companyRow = (company: CrmCompany) => (
    <div key={company.id}>
      <div className="crm-company-row">
        <div><strong>{company.name}</strong><small>{company.isPrimary && t("crm.primary")}</small></div>
        <code>{company.externalCompanyId}</code>
        <div className="crm-actions-inline">
          <span className={company.isActive ? "crm-status" : "crm-section-note"}>
            {company.isActive ? t("crm.active") : t("crm.inactive")}
          </span>
          {!company.isPrimary && company.isActive && !disabled && (
            <button className="link" type="button" onClick={() => onUpdate(company.id, { isPrimary: true })}>
              {t("crm.set_primary")}
            </button>
          )}
          {!disabled && <button className="link" type="button"
            onClick={() => setEditing(editing === company.id ? null : company.id)}>
            {t("crm.edit_company")}
          </button>}
        </div>
      </div>
      {editing === company.id && (
        <CrmCompanyForm key={company.id} company={company} disabled={disabled}
          onSave={(name, externalCompanyId) => { onUpdate(company.id, { name, externalCompanyId }); setEditing(null); }}
          onRemove={() => { onRemove(company.id); setEditing(null); }}
          onCancel={() => setEditing(null)} />
      )}
    </div>
  );
  return (
    <div>
      {primary && <><h3 className="crm-section-title">{t("crm.primary_company")}</h3>{companyRow(primary)}</>}
      {other.length > 0 && <><h3 className="crm-section-title">{t("crm.other_companies")}</h3>
        {other.map(companyRow)}</>}
      {companies.filter((item) => item.isActive).length === 1 && (
        <p className="crm-section-note">{t("crm.single_hint")}</p>
      )}
      {!disabled && (
        <button type="button" className="link has-icon" onClick={() => setEditing("new")}>
          {t("crm.add_company")}
        </button>
      )}
      {editing === "new" && (
        <CrmCompanyForm disabled={disabled}
          onSave={(name, externalId) => { onCreate(name, externalId); setEditing(null); }}
          onCancel={() => setEditing(null)} />
      )}
    </div>
  );
}
