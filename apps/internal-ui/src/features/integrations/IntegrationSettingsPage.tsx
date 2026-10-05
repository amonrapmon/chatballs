import { t } from "../../i18n";
import { ContentState } from "../../shared/ui";
import { Icon } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import { useIntegrations } from "../settings/useIntegrations";
import { WebIntegrationPage } from "./WebIntegrationPage";
import { ExternalServerPage } from "./external/ExternalServerPage";
import type { ServerKind } from "./external/types";
import { ServerPageLoading } from "./external/ServerPageLoading";

export function IntegrationSettingsPage({ integrationId, createKind, onCreated, onOpenSettings, onBack }: {
  integrationId?: number; createKind?: ServerKind; onCreated: (id: number) => void; onOpenSettings: () => void; onBack: () => void;
}) {
  const list = useIntegrations(true);
  const integration = list.items.find((i) => i.id === integrationId);
  if (list.loading) return <ServerPageLoading />;
  if (list.failed || (!createKind && !integration)) return <ContentState
    className={`server-page-state${list.failed ? " is-error" : ""}`} icon={<Icon name={list.failed ? "warning" : "server"} size={18} />}
    title={t(list.failed ? "servers.load_failed" : "servers.not_found")}
    text={t(list.failed ? "servers.load_failed_hint" : "servers.not_found_hint")}
    action={list.failed ? <Button variant="secondary" onClick={list.reload}>{t("common.try_again")}</Button>
      : <button className="link" type="button" onClick={onBack}>{t("servers.back")}</button>} />;
  if (integration?.provider === "WEB") return <WebIntegrationPage integrationId={integration.id} onOpenSettings={onOpenSettings} onBack={onBack} />;
  if (createKind || integration?.externalServer) return <ExternalServerPage key={integration?.id ?? createKind} initial={integration ?? null}
    kind={createKind ?? integration!.externalServer!.type} integrations={list.items} onCreated={onCreated} onOpenSettings={onOpenSettings} onBack={onBack} />;
  return <ContentState icon={<Icon name="server" size={28} />} title={t("servers.not_found")} text={t("servers.not_found_hint")}
    action={<Button variant="secondary" onClick={onBack}>{t("servers.back")}</Button>} />;
}
