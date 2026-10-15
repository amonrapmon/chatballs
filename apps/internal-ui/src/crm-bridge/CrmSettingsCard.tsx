import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../api/client";
import { t } from "../i18n";
import { SelectField } from "../shared/form-controls";
import { Button } from "../shared/ui-controls";
import { LoadingState } from "../shared/ui";
import type { Integration } from "../features/integrations/model";
import {
  assignCrmCompany, createCrmCompany, loadCrm, removeCrmCompany,
  saveCrmProvider, unassignCrmCompany, updateCrmCompany,
} from "./api";
import type { CrmConfiguration, CrmProvider } from "./model";
import { CrmCompanies } from "./CrmCompanies";
import { CrmBindings } from "./CrmBindings";

const PROVIDERS: Array<[CrmProvider, string]> = [
  ["NONE", t("crm.none")], ["YCLIENTS", "YCLIENTS"], ["DIKIDI", "DIKIDI"],
];
const errors: Record<string, string> = {
  provider_has_existing_companies: t("crm.provider_conflict"),
  company_has_bindings: t("crm.company_conflict"),
  reassign_primary_first: t("crm.reassign_primary"),
  crm_disabled: t("crm.disabled_action"),
  configuration_conflict: t("crm.company_conflict"),
  invalid_configuration: t("crm.company_required"),
  invalid_external_company_id: t("crm.company_required"),
  invalid_company_name: t("crm.company_required"),
};

function errorText(problem: unknown): string {
  if (problem instanceof ApiError) {
    const code = problem.payload.code;
    return typeof code === "string" ? errors[code] ?? t("crm.failed_save") : t("crm.failed_save");
  }
  return t("crm.failed_save");
}

export function CrmSettingsCard({ connections, canManage }: {
  connections: Integration[]; canManage: boolean;
}) {
  const [config, setConfig] = useState<CrmConfiguration | null>(null);
  const [provider, setProvider] = useState<CrmProvider>("NONE");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const refresh = useCallback(async () => {
    const latest = await loadCrm();
    setConfig(latest);
    setProvider(latest.provider);
  }, []);

  useEffect(() => {
    let active = true;
    loadCrm().then((latest) => {
      if (active) { setConfig(latest); setProvider(latest.provider); }
    }).catch(() => {
      if (active) setError(t("crm.failed_load"));
    });
    return () => { active = false; };
  }, []);

  async function run(action: () => Promise<unknown>) {
    if (busy || !canManage) return;
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setBusy(false);
    }
  }
  const companies = config?.companies ?? [];
  const activeCompanies = companies.filter((item) => item.isActive);
  const showBindings = companies.length > 1 || Boolean(config?.bindings.length);

  return (
    <section className="administration-card crm-settings-card">
      <header className="crm-section-head">
        <div><strong>{t("crm.title")}</strong><p>{t("crm.subtitle")}</p></div>
        {config && <span className="crm-status">
          {config.provider === "NONE" ? t("crm.off") : t("crm.connected")}
        </span>}
      </header>
      {!config ? (
        error ? <p className="crm-error" role="alert">{error}</p> : <LoadingState />
      ) : (
        <>
          <SelectField
            label={t("crm.provider")}
            value={provider}
            options={PROVIDERS}
            disabled={!canManage || busy}
            onChange={(value) => setProvider(value as CrmProvider)}
          />
          {config.provider === "NONE" && provider === "NONE" ? (
            <div className="crm-section-note">
              <strong>{t("crm.off_title")}</strong>
              <p>{t("crm.off_hint")}</p>
            </div>
          ) : config.provider !== "NONE" && provider === config.provider ? (
            <>
              <CrmCompanies
                companies={companies} disabled={busy || !canManage}
                onCreate={(name, id) => run(() => createCrmCompany(name, id))}
                onUpdate={(id, changes) => run(() => updateCrmCompany(id, changes))}
                onRemove={(id) => run(() => removeCrmCompany(id))}
              />
              {showBindings && (
                <CrmBindings
                  companies={activeCompanies} connections={connections}
                  requireBinding={activeCompanies.length > 1}
                  bindings={config.bindings} disabled={busy || !canManage}
                  onAssign={(connectionId, companyId) => run(
                    () => companyId ? assignCrmCompany(connectionId, companyId)
                      : unassignCrmCompany(connectionId)
                  )}
                />
              )}
            </>
          ) : null}
          {error && <p className="crm-error" role="alert">{error}</p>}
          {canManage && (
            <div className="crm-form-actions">
              <Button variant="primary" disabled={busy || provider === config.provider}
                onClick={() => void run(() => saveCrmProvider(provider))}>
                {t("crm.save")}
              </Button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
