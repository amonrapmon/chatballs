import { useEffect, useState } from "react";
import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { fetchTransfer, type TransferRecord } from "./api";

export function TransferTimelineEvent({ conversationId, transferId, fallback, createdAt }: {
  conversationId: number; transferId: number; fallback: string; createdAt: string;
}) {
  const [transfer, setTransfer] = useState<TransferRecord | null>(null);
  useEffect(() => {
    let active = true;
    void fetchTransfer(conversationId, transferId).then(({ transfer: row }) => {
      if (active) setTransfer(row);
    }).catch(() => { /* Show only the safe system event if access was revoked. */ });
    return () => { active = false; };
  }, [conversationId, transferId]);
  const text = transfer?.initiatedBy && transfer.newOperator
    ? `${t("transfers.history_entry", { from: transfer.initiatedBy.name, to: transfer.newOperator.name })} · ${transfer.reason.name}`
    : fallback;
  return <div className="sales-event-chip claimed"><Icon name="transfer" size={12} />{text}<span>·</span>{fmt.time(createdAt)}</div>;
}
