import { useState } from "react";
import { fmt, t, tn } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { ContentState } from "../../../shared/ui";
import { Button } from "../../../shared/ui-controls";
import { McpToolRow } from "./McpToolRow";
import { ReadOnlyDialog } from "./ReadOnlyDialog";
import type { McpTool } from "./types";
import type { ServerEditor } from "./useServerEditor";
import { serverHost } from "./model";

export function McpTools({ editor, openConnection }: { editor: ServerEditor; openConnection: () => void }) {
  const [confirming, setConfirming] = useState<McpTool | null>(null);
  const server = editor.integration?.externalServer;
  const tools = server?.tools ?? [];
  const state = server?.toolsState ?? "not_loaded";
  const stale = ["unreachable", "unauthorized", "address_forbidden"].includes(state);
  const read = tools.filter((tool) => tool.readOnlyHint || tool.readOnlyConfirmation).length;
  const refresh = () => void editor.action("tools/refresh/");
  return <div className="portal-settings-inner server-content">
    <div className="portal-settings-heading server-tools-heading">
      <div><h3>{t("ai.tools")}</h3><p>{t("servers.tools_lead")}</p></div>
      <Button variant="secondary" icon="refresh" disabled={editor.busy || !editor.integration || editor.dirty} onClick={refresh}>{t("servers.refresh")}</Button>
    </div>
    {editor.error && <div className="server-errors" role="alert">{editor.error}</div>}
    <div className="server-tools-card">
      {editor.refreshing ? <div className="server-tools-skeleton" aria-busy="true"><small>{t("servers.refreshing")}</small>{[1, 2, 3].map((i) => <div key={i}><i /><span><i /><i /></span></div>)}</div> : <>
        {stale && <div className={`server-state-banner${state === "address_forbidden" ? " is-warning" : ""}`} role="alert">
          <Icon name={state === "unauthorized" ? "lock" : "warning"} size={17} />
          <div><strong>{t(`servers.${state as "unreachable" | "unauthorized" | "address_forbidden"}`)}</strong><small>{t(state === "unauthorized" ? "servers.authorization_hint" : state === "address_forbidden" ? "servers.forbidden_hint" : "servers.unreachable_hint", { host: serverHost(server?.url ?? "") })}</small>
            <Button variant="secondary" className="server-error-action" disabled={editor.busy} onClick={state === "unreachable" ? refresh : openConnection}>{t(state === "unreachable" ? "common.try_again" : state === "address_forbidden" ? "servers.change_address" : "servers.open_connection")}</Button></div>
        </div>}
        {tools.length > 0 && <>
          {!stale && <div className="server-tools-summary"><div><strong>{tn("servers.count", tools.length)}</strong><small>{tn("servers.read_count", read)} · {tn("servers.write_count", tools.length - read)}</small></div>
            {server?.toolsRefreshedAt && <small>{t("servers.refreshed", { time: fmt.shortDateTime(server.toolsRefreshedAt) })}</small>}
          </div>}
          {tools.map((tool) => <McpToolRow key={tool.name} tool={tool} busy={editor.busy} stale={stale}
            onConfirm={() => setConfirming(tool)} onRevoke={() => void editor.action("tools/read-only/revoke/", { name: tool.name })} />)}
          <div className="server-card-note">{stale && server?.toolsRefreshedAt ? t("servers.stale", { time: fmt.shortDateTime(server.toolsRefreshedAt) }) : t("servers.read_note")}</div>
        </>}
        {tools.length === 0 && <ContentState icon={<Icon name="wrench" size={24} />}
          title={t(state === "no_tools" ? "servers.no_tools" : "servers.not_loaded")}
          text={t(state === "no_tools" ? "servers.no_tools_hint" : "servers.not_loaded_hint")}
          action={<Button variant="secondary" disabled={editor.busy || !editor.integration || editor.dirty} onClick={refresh}>{t(state === "no_tools" ? "servers.refresh" : "servers.load")}</Button>} />}
      </>}
    </div>
    {confirming && <ReadOnlyDialog key={confirming.name} tool={confirming} busy={editor.busy} onClose={() => setConfirming(null)}
      onConfirm={() => void editor.action("tools/read-only/confirm/", { name: confirming.name, confirmed: true }).then((success) => { if (success) setConfirming(null); })} />}
  </div>;
}
