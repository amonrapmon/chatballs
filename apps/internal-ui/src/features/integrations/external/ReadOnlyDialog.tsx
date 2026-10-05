import { Checkbox } from "antd";
import { useState } from "react";
import { t } from "../../../i18n";
import { DecisionDialog } from "../../../shared/DecisionDialog";
import { Button } from "../../../shared/ui-controls";
import type { McpTool } from "./types";

export function ReadOnlyDialog({ tool, busy, onClose, onConfirm }: {
  tool: McpTool; busy: boolean; onClose: () => void; onConfirm: () => void;
}) {
  const [confirmed, setConfirmed] = useState(false);
  return <DecisionDialog open centered width={560} className="server-confirm-dialog" tone="warning" icon="danger"
    title={t("servers.confirm_title", { name: tool.title || tool.name })} description={t("servers.confirm_lead")}
    onClose={() => { if (!busy) onClose(); }} actions={<>
      <Button variant="secondary" disabled={busy} onClick={onClose}>{t("common.cancel")}</Button>
      <Button variant="primary" disabled={!confirmed || busy} onClick={() => { if (confirmed && !busy) onConfirm(); }}>{t("admin.confirm")}</Button>
    </>}>
    <div className="server-confirmation">
      <div className="server-warning"><p>{t("servers.confirm_risk")}</p></div>
      <Checkbox className="server-confirm-check" checked={confirmed} disabled={busy} onChange={(event) => setConfirmed(event.target.checked)}>{t("servers.confirm_check")}</Checkbox>
      <small>{t("servers.confirm_audit")}</small>
    </div>
  </DecisionDialog>;
}
