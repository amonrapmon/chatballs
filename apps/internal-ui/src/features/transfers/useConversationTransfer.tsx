import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import type { ApiConversation } from "../conversations/model";
import { TransferDialog } from "./TransferDialog";

export function useConversationTransfer(detail: ApiConversation | null, onUpdated: (next: ApiConversation) => void, onRefresh: () => void, retainsReplyAfterTransfer: boolean) {
  const [open, setOpen] = useState(false);
  const [transferredName, setTransferredName] = useState("");
  useEffect(() => {
    if (!transferredName) return;
    const timer = window.setTimeout(() => setTransferredName(""), 4000);
    return () => window.clearTimeout(timer);
  }, [transferredName]);
  const available = detail?.lifecycle === "OPEN" && !!detail.access?.actions.includes("conversations.transfer");
  useEffect(() => { if (!available) setOpen(false); }, [available]);
  return {
    available,
    open: () => setOpen(true),
    overlay: <>{transferredName && <div className="transfer-success" role="status"><Icon name="check" size={15} />{t("transfers.success", { name: transferredName })}</div>}
      {detail && open && <TransferDialog key={detail.id} detail={detail} retainsReplyAfterTransfer={retainsReplyAfterTransfer} onUpdated={onUpdated} onClose={() => setOpen(false)}
        onTransferred={(name) => { setOpen(false); onRefresh(); setTransferredName(name); }} />}</>,
  };
}
