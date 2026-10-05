import { Modal } from "antd";
import { useState } from "react";
import { t } from "../../../i18n";
import { Button } from "../../../shared/ui-controls";
import { Icon } from "../../../shared/icons";
import type { McpTool } from "./types";

export function ReadOnlyDialog({ tool, busy, onClose, onConfirm }: {
  tool: McpTool; busy: boolean; onClose: () => void; onConfirm: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  return <Modal open width={560} className="server-confirm-modal" closable={false}
    title={<div className="server-confirm-heading"><span><Icon name="warning" size={22} /></span><div><strong>{t("servers.confirm_title", { name: tool.title || tool.name })}</strong><p>{t("servers.confirm_lead")}</p></div></div>}
    onCancel={onClose} footer={<>
      <Button variant="secondary" disabled={busy} onClick={onClose}>{t("common.cancel")}</Button>
      <Button variant="primary" disabled={!confirmed || busy} onClick={onConfirm}>{t("admin.confirm")}</Button>
    </>}>
    <div className="server-confirmation">
      <div className="server-warning"><p>{t("servers.confirm_risk")}</p></div>
      <label className="server-confirm-check"><input type="checkbox" checked={confirmed} disabled={busy} onChange={(event) => setConfirmed(event.target.checked)} />{t("servers.confirm_check")}</label>
      <small>{t("servers.confirm_audit")}</small>
    </div>
  </Modal>;
}
