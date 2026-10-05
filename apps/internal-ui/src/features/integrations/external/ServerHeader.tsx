import { t, tn } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { CopyButton } from "../../../shared/ui-controls";
import { StatusPill } from "../../../shared/ui";
import type { ServerEditor } from "./useServerEditor";

export function ServerHeader({ editor, onOpenSettings, onBack }: { editor: ServerEditor; onOpenSettings: () => void; onBack: () => void }) {
  const server = editor.integration?.externalServer ?? editor.draft.externalServer;
  const mcp = server.type === "mcp";
  const name = editor.integration?.name || t(mcp ? "servers.new_mcp" : "servers.new_http");
  const status = !editor.integration ? "draft" : !editor.integration.isActive ? "disabled" : editor.integration.status === "OK" ? "healthy" : editor.integration.status === "ERROR" ? "error" : "unchecked";
  return <header className="web-integration-head">
    <nav className="portal-breadcrumbs">
      <button className="link is-strong" type="button" onClick={onOpenSettings}>{t("common.settings")}</button><span>/</span>
      <button className="link is-muted" type="button" onClick={onBack}>{t("common.integrations")}</button><span>/</span><b>{name}</b>
    </nav>
    <div className="web-integration-title">
      <span className="server-title-icon"><Icon name={mcp ? "server" : "swap"} size={17} /></span><h2>{name}</h2>
      <StatusPill status={status} label={status === "healthy" ? t("common.connected") : status === "unchecked" ? t("ai.not_checked") : undefined} /><span className="web-integration-agent">{t(mcp ? "servers.new_mcp" : "servers.new_http")} · {tn("servers.count", mcp ? server.tools?.length ?? 0 : 1)}</span>
    </div>
    {server.url && <div className="web-integration-embed"><span className="web-integration-embed-code"><code>{mcp ? "" : `${server.method ?? "GET"} `}{server.url}</code><CopyButton value={server.url} className="web-integration-copy" /></span><span>{t(mcp ? "servers.address_note" : "servers.request_note")}</span></div>}
  </header>;
}
