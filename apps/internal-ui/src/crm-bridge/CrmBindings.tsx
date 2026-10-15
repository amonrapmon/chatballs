import { t } from "../i18n";
import { SelectField } from "../shared/form-controls";
import type { Integration } from "../features/integrations/model";
import type { CrmBinding, CrmCompany } from "./model";

export function CrmBindings({ companies, connections, bindings, disabled, onAssign }: {
  companies: CrmCompany[]; connections: Integration[]; bindings: CrmBinding[];
  disabled: boolean; onAssign: (connectionId: number, companyId: number) => void;
}) {
  const messengers = connections.filter((item) => item.kind === "MESSENGER");
  const hasUnbound = messengers.some((item) => !bindings.some((binding) => binding.integrationId === item.id));
  const options: Array<[string, string]> = [
    ["", t("crm.choose_company")], ...companies.map((item): [string, string] => [String(item.id), item.name]),
  ];
  return (
    <div>
      <h3 className="crm-section-title">{t("crm.bindings")}</h3>
      <p className="crm-section-note">{t("crm.binding_hint")}</p>
      <table className="crm-table">
        <thead><tr><th>{t("crm.connection")}</th><th>{t("crm.company")}</th></tr></thead>
        <tbody>
          {messengers.map((item) => (
            <tr key={item.id}><td><strong>{item.name}</strong><small>{item.provider}</small></td>
              <td className="crm-branch-cell">
                <SelectField
                  label={t("crm.company")} value={String(
                    bindings.find((binding) => binding.integrationId === item.id)?.companyId ?? ""
                  )} options={options} disabled={disabled}
                  onChange={(value) => onAssign(item.id, value ? Number(value) : 0)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {hasUnbound && <p className="crm-notice">
        <strong>{t("crm.unbound")}</strong> {t("crm.unbound_hint")}
      </p>}
      <p className="crm-section-note">{t("crm.no_primary_guess")}</p>
    </div>
  );
}
