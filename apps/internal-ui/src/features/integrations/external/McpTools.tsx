import { useState } from "react";
import { fmt, t, tn } from "../../../i18n";
import { Button } from "../../../shared/ui-controls";
import { McpToolRow } from "./McpToolRow";
import { ReadOnlyDialog } from "./ReadOnlyDialog";
import { isToolsError, McpToolsEmpty, McpToolsError, McpToolsLoading } from "./McpToolsState";
import type { McpTool } from "./types";
import type { ServerEditor } from "./useServerEditor";

type ToolsEditor = Pick<ServerEditor, "integration" | "busy" | "refreshing" | "dirty" | "error" | "action">;

export function McpTools({ editor, openConnection }: { editor: ToolsEditor; openConnection: () => void }) {
  const [confirming, setConfirming] = useState<McpTool | null>(null);
  const server = editor.integration?.externalServer;
  const tools = server?.tools ?? [];
  const state = server?.toolsState ?? "not_loaded";
  const stale = isToolsError(state);
  const read = tools.filter((tool) => tool.readOnlyHint || tool.readOnlyConfirmation).length;
  const refresh = () => void editor.action("tools/refresh/");
  return <div className="portal-settings-inner server-content">
    <div className="portal-settings-heading server-tools-heading">
      <div><h3>{t("ai.tools")}</h3><p>{t("servers.tools_lead")}</p></div>
      <Button variant="secondary" icon="refresh" disabled={editor.busy || !editor.integration || editor.dirty} onClick={refresh}>{t("servers.refresh")}</Button>
    </div>
    {editor.error && <div className="server-errors" role="alert">{editor.error}</div>}
    <div className="server-tools-card">
      {editor.refreshing ? <McpToolsLoading /> : <>
        {stale && <McpToolsError state={state} url={server?.url ?? ""} busy={editor.busy} refresh={refresh} openConnection={openConnection} />}
        {tools.length > 0 && <>
          {!stale && <div className="server-tools-summary"><div><strong>{tn("servers.count", tools.length)}</strong><small>{tn("servers.read_count", read)} · {tn("servers.write_count", tools.length - read)}</small></div>
            {server?.toolsRefreshedAt && <span className="server-tools-updated"><i />{t("servers.refreshed", { time: fmt.shortDateTime(server.toolsRefreshedAt) })}</span>}
          </div>}
          {tools.map((tool) => <McpToolRow key={tool.name} tool={tool} busy={editor.busy} stale={stale}
            onConfirm={() => setConfirming(tool)} onRevoke={() => void editor.action("tools/read-only/revoke/", { name: tool.name })} />)}
          <div className="server-card-note">{stale && server?.toolsRefreshedAt ? t(state === "unreachable" ? "servers.stale_unreachable" : state === "unauthorized" ? "servers.stale_unauthorized" : "servers.stale", { time: fmt.shortDateTime(server.toolsRefreshedAt) }) : t("servers.read_note")}</div>
        </>}
        {tools.length === 0 && <McpToolsEmpty state={state} disabled={editor.busy || !editor.integration || editor.dirty} refresh={refresh} />}
      </>}
    </div>
    {confirming && <ReadOnlyDialog key={confirming.name} tool={confirming} busy={editor.busy} onClose={() => setConfirming(null)}
      onConfirm={() => void editor.action("tools/read-only/confirm/", { name: confirming.name, confirmed: true }).then((success) => { if (success) setConfirming(null); })} />}
  </div>;
}
