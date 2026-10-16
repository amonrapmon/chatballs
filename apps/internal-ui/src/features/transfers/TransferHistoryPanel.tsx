import { useEffect, useRef, useState } from "react";
import { t } from "../../i18n";
import { usePagedResource } from "../../shared/usePagedResource";
import { useRealtimeEvent } from "../realtime/RealtimeProvider";
import { fetchTransfers } from "./api";
import { TransferHistoryRows } from "./TransferHistoryRows";
import { ActivityHistoryDialog } from "./ActivityHistoryDialog";
import "./styles.css";

export function TransferHistoryPanel({ conversationId, assignmentVersion }: {
  conversationId: number; assignmentVersion: number;
}) {
  const list = usePagedResource((page) => fetchTransfers(conversationId, page), { conversationId });
  const [open, setOpen] = useState(false);
  const previous = useRef(assignmentVersion);
  useEffect(() => {
    if (previous.current !== assignmentVersion) { previous.current = assignmentVersion; void list.reload(); }
  }, [assignmentVersion]);
  useRealtimeEvent("conversation.changed", (event) => {
    if (event.conversationId === conversationId) void list.reload();
  });
  return <section className="transfer-history-panel">
    <div className="transfer-history-head"><h4>{t("transfers.history_title")}</h4>
      <button className="link" type="button" onClick={() => setOpen(true)}>{t("transfers.full_history")}</button>
    </div>
    {list.errorText && <p className="transfer-error">{list.errorText}</p>}
    <TransferHistoryRows items={list.items.slice(0, 3)} />
    {open && <ActivityHistoryDialog key={conversationId} conversationId={conversationId} onClose={() => setOpen(false)} />}
  </section>;
}
