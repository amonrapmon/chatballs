import { Dropdown } from "antd";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import type { ServerKind } from "./external/types";
import "./add-integration.css";

export function AddIntegrationButton({ onEntry, onServer }: { onEntry: () => void; onServer: (kind: ServerKind) => void }) {
  const option = (icon: "message" | "server" | "swap", title: string, hint: string, action: () => void) =>
    <button type="button" onClick={action}><i><Icon name={icon} size={15} /></i><span><strong>{title}</strong><small>{hint}</small></span></button>;
  return <Dropdown trigger={["click"]} overlayClassName="app-dropdown is-server-add" menu={{ items: [
    { type: "group", label: t("servers.entry"), children: [
      { key: "entry", label: option("message", t("servers.entry_title"), t("servers.entry_hint"), onEntry) },
    ] },
    { type: "divider" },
    { type: "group", label: t("servers.external_group"), children: [
      { key: "mcp", label: option("server", t("servers.new_mcp"), t("servers.mcp_hint"), () => onServer("mcp")) },
      { key: "http", label: option("swap", t("servers.new_http"), t("servers.http_hint"), () => onServer("http")) },
    ] },
  ] }}><Button variant="primary" icon="plus">{t("servers.add")}<Icon name="chevron" size={14} /></Button></Dropdown>;
}
