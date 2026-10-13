import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { providerLabel } from "../../shared/providers";
import { Button } from "../../shared/ui-controls";
import { SmallAvatar } from "../conversations/assigneeOptions";
import type { AppNotification } from "../notifications/model";
import { fetchTransfer, type TransferRecord } from "./api";
import "./notification.css";

export function TransferNotificationCard({ item, onOpen }: {
  item: AppNotification; onOpen: () => void;
}) {
  const [transfer, setTransfer] = useState<TransferRecord | null>(null);
  useEffect(() => {
    let active = true;
    if (item.transferId) void fetchTransfer(Number(item.targetId), item.transferId)
      .then((result) => { if (active) setTransfer(result.transfer); })
      .catch(() => { /* Access may have changed: keep the safe notification. */ });
    return () => { active = false; };
  }, [item.targetId, item.transferId]);
  const sender = transfer?.initiatedBy;
  return <div className="transfer-notification-card">
    {sender && <SmallAvatar name={sender.name} avatarUrl={sender.avatarUrl} />}
    <div>
      <strong>{sender ? t("transfers.notification_title", { name: sender.name }) : item.title}</strong>
      {transfer ? <>
        <p>{transfer.conversation.contactName}{transfer.conversation.provider && <> · {providerLabel(transfer.conversation.provider)}</>}</p>
        <p className="transfer-notification-reason"><b>{transfer.reason.name}</b>{transfer.comment && <> {transfer.comment}</>}</p>
      </> : item.body && <p>{item.body}</p>}
      <div className="transfer-notification-actions">
        <Button variant="primary" onClick={onOpen}>{t("transfers.open_dialog")}</Button>
        <small>{t("transfers.just_now")}</small>
      </div>
    </div>
  </div>;
}
