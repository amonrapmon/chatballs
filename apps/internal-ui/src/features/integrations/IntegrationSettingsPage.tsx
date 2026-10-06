import { useIntegrations } from "../settings/useIntegrations";
import { WebIntegrationPage } from "./WebIntegrationPage";
import { ExternalServerPage } from "./external/ExternalServerPage";
import type { ServerKind } from "./external/types";
import { ServerPageLoading } from "./external/ServerPageLoading";
import { ServerPageState } from "./external/ServerPageState";

export function IntegrationSettingsPage({ integrationId, createKind, onCreated, onOpenSettings, onBack }: {
  integrationId?: number; createKind?: ServerKind; onCreated: (id: number) => void; onOpenSettings: () => void; onBack: () => void;
}) {
  const list = useIntegrations(true);
  const integration = list.items.find((i) => i.id === integrationId);
  if (list.loading) return <ServerPageLoading />;
  if (list.failed || (!createKind && !integration)) return <ServerPageState failed={list.failed} onRetry={list.reload} onBack={onBack} />;
  if (integration?.provider === "WEB") return <WebIntegrationPage integrationId={integration.id} onOpenSettings={onOpenSettings} onBack={onBack} />;
  if (createKind || integration?.externalServer) return <ExternalServerPage key={integration?.id ?? createKind} initial={integration ?? null}
    kind={createKind ?? integration!.externalServer!.type} integrations={list.items} onCreated={onCreated} onOpenSettings={onOpenSettings} onBack={onBack} />;
  return <ServerPageState onRetry={list.reload} onBack={onBack} />;
}
