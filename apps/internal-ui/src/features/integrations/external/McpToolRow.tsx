import { Dropdown } from "antd";
import { fmt, t } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import type { McpTool } from "./types";

export function McpToolRow({ tool, busy, stale, onConfirm, onRevoke }: {
  tool: McpTool; busy: boolean; stale: boolean; onConfirm: () => void; onRevoke: () => void;
}) {
  const readOnly = tool.readOnlyHint || Boolean(tool.readOnlyConfirmation);
  if (stale) return <div className="server-tool-row is-stale"><span className="server-tool-icon"><Icon name="wrench" size={15} /></span><strong>{tool.title || tool.name}</strong></div>;
  return <div className={`server-tool-row${stale ? " is-stale" : ""}`}>
    <span className="server-tool-icon"><Icon name="wrench" size={15} /></span>
    <div className="server-tool-description">
      <div><strong>{tool.title || tool.name}</strong><code>{tool.name}</code></div>
      <small>{tool.description}</small>
      {tool.readOnlyConfirmation && <small className="server-tool-confirmed">{t("servers.confirmed", {
        name: tool.readOnlyConfirmation.confirmedBy?.name ?? "—", time: fmt.shortDateTime(tool.readOnlyConfirmation.confirmedAt),
      })}</small>}
    </div>
    <div className="server-tool-permission">
      <span className={`server-read-badge${readOnly ? " is-read" : ""}`}><Icon name={readOnly ? "eye" : "warning"} size={12} />{t(readOnly ? "servers.read_only" : "servers.may_write")}</span>
      {!readOnly && <button className="link" type="button" disabled={busy} onClick={onConfirm}>{t("servers.confirm_read")}</button>}
    </div>
    {tool.readOnlyConfirmation && <Dropdown trigger={["click"]} overlayClassName="app-dropdown" menu={{ items: [
      { key: "revoke", label: t("servers.revoke"), disabled: busy, onClick: onRevoke },
    ] }}><button className="row-menu-button" type="button" aria-label={t("settings.integration_actions")}><Icon name="more" /></button></Dropdown>}
  </div>;
}
