import { Modal } from "antd";
import { useState } from "react";
import { t } from "../../i18n";
import type { ActivityFilter } from "./activityApi";
import { ActivityHistoryList } from "./ActivityHistoryList";
import "./activity-history.css";

const TABS = { all: "transfers.all", transfers: "transfers.history_tab", participants: "transfers.participants_tab" } as const;

export function ActivityHistoryDialog({ conversationId, onClose }: { conversationId: number; onClose: () => void }) {
  const [kind, setKind] = useState<ActivityFilter>("all");
  return <Modal open width={420} footer={null} title={null} closable={false} maskClosable keyboard
    onCancel={onClose} className="activity-history-modal" aria-labelledby="activity-history-title">
    <section className="activity-history-card">
      <header><h3 id="activity-history-title">{t("transfers.history_dialog")}</h3>
        <div className="activity-history-tabs" role="tablist" aria-label={t("transfers.history_dialog")}>
          {(Object.keys(TABS) as ActivityFilter[]).map((tab) => <button key={tab} role="tab" type="button"
            aria-selected={kind === tab} onClick={() => setKind(tab)}>{t(TABS[tab])}</button>)}
        </div>
      </header>
      <ActivityHistoryList key={kind} conversationId={conversationId} kind={kind} />
    </section>
  </Modal>;
}
