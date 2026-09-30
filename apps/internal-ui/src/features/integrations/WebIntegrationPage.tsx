import { useState } from "react";
import "../support-portals/styles-detail.css";
import "../support-portals/styles-settings.css";

import { t } from "../../i18n";
import { SectionMenu, type SectionMenuItem } from "../../shared/SectionMenu";
import { EmptyState, LoadingState } from "../../shared/ui";
import { DeleteIntegrationDialog } from "./DeleteIntegrationDialog";
import { WebIntegrationBasics } from "./WebIntegrationBasics";
import { WebIntegrationHeader } from "./WebIntegrationHeader";
import { useWebIntegration } from "./useWebIntegration";

type Section = "basics" | "fields" | "form" | "look" | "danger";

const sections: SectionMenuItem<Section>[] = [
  { key: "basics", label: t("portals.basics"), icon: "settings" },
  { key: "fields", label: t("settings.site_data"), icon: "code", disabled: true },
  { key: "form", label: t("settings.pre_chat_form"), icon: "doc", disabled: true },
  { key: "look", label: t("common.appearance"), icon: "paint", disabled: true, divider: true },
  { key: "danger", label: t("settings.delete_connection"), icon: "trash", danger: true },
];

export function WebIntegrationPage({ integrationId, onOpenSettings, onBack }: {
  integrationId: number;
  onOpenSettings: () => void;
  onBack: () => void;
}) {
  const { integration, loading, failed, setIntegration } = useWebIntegration(integrationId);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  if (loading) return <LoadingState />;
  if (failed) return <EmptyState title={t("settings.could_not_load_integrations")} />;
  if (!integration) return <EmptyState title={t("settings.web_integration_not_found")} />;

  return (
    <section className="web-integration-page">
      <WebIntegrationHeader integration={integration} onOpenSettings={onOpenSettings} onBack={onBack} />
      <div className="portal-settings-layout">
        <SectionMenu
          items={sections}
          activeKey="basics"
          note={t("settings.web_changes_apply_after_save")}
          onSelect={(section) => { if (section === "danger") setConfirmingDelete(true); }}
        />
        <div className="portal-settings-content">
          <div className="portal-settings-inner">
            <div className="portal-settings-heading">
              <h3>{t("portals.basics")}</h3>
            </div>
            <WebIntegrationBasics key={integration.id} integration={integration} onSaved={setIntegration} />
          </div>
        </div>
      </div>
      {confirmingDelete && <DeleteIntegrationDialog integration={integration} onClose={() => setConfirmingDelete(false)} onDeleted={onBack} />}
    </section>
  );
}
