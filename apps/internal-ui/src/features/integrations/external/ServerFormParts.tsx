import { fmt, t, tn } from "../../../i18n";
import { SwitchButton } from "../../../shared/form-controls";
import { Button } from "../../../shared/ui-controls";
import type { ServerEditor } from "./useServerEditor";

export function ServerEnabled({ editor }: { editor: ServerEditor }) {
  const mcp = editor.draft.externalServer.type === "mcp";
  return <div className="server-enabled">
    <span><strong>{t(mcp ? "servers.enabled" : "servers.http_enabled")}</strong><small>{t(mcp ? "servers.enabled_hint" : "servers.http_enabled_hint")}</small></span>
    <SwitchButton className="ui-switch" label={t(mcp ? "servers.enabled" : "servers.http_enabled")} checked={editor.draft.isActive} disabled={editor.busy}
      onClick={() => editor.change({ ...editor.draft, isActive: !editor.draft.isActive })} />
  </div>;
}

export function ServerErrors({ messages }: { messages?: string[] }) {
  return messages?.length ? <div className="server-errors" role="alert">{messages.map((message, index) => <small key={index}>{message}</small>)}</div> : null;
}

export function ServerSaveActions({ editor, mcp = false }: { editor: ServerEditor; mcp?: boolean }) {
  const count = Object.values(editor.errors).reduce((n, items) => n + items.length, 0);
  return <>
    {editor.error && <div className="integration-form-error" role="alert">{editor.error}</div>}
    <div className="server-actions">
      <Button variant="primary" disabled={editor.busy || count > 0} onClick={() => void editor.save()}>{t(editor.busy ? "common.saving" : "common.save")}</Button>
      {mcp && <Button variant="secondary" icon="refresh" disabled={editor.busy || !editor.integration || editor.dirty}
        title={!editor.integration || editor.dirty ? t("servers.save_first") : undefined}
        onClick={() => void editor.action("test/")}>{t("servers.test")}</Button>}
      <span className="server-action-note">
        {count > 0 ? tn("servers.fix_errors", count) : editor.saved ? t("portals.settings_saved")
          : mcp && editor.integration?.status === "OK" && editor.integration.lastCheckedAt
            ? t("servers.connected", { time: fmt.shortDateTime(editor.integration.lastCheckedAt) }) : ""}
      </span>
    </div>
    {mcp && editor.integration?.status === "ERROR" && <div className="server-errors" role="alert">{editor.integration.lastError}</div>}
  </>;
}
