import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import type { ActivityRecord } from "./activityApi";

export function ActivityHistoryRow({ item }: { item: ActivityRecord }) {
  const from = item.actor?.name || t("conversations.not_set");
  const to = item.recipient?.name || t("conversations.not_set");
  const title = item.kind === "CLAIM" ? t("transfers.queue_claim_entry", { name: from })
    : item.kind === "TRANSFER" ? t("transfers.history_entry", { from, to })
    : t(item.kind === "JOIN" ? "transfers.participant_join_entry" : "transfers.participant_leave_entry", { from, to });
  return <article className="activity-history-row" data-activity-id={item.id}>
    <span className={`activity-history-icon ${item.kind === "TRANSFER" ? "is-transfer" : ""}`}>
      <Icon name={item.kind === "TRANSFER" ? "transfer" : item.kind === "JOIN" ? "team" : item.kind === "LEAVE" ? "close" : "check"} size={13} strokeWidth={2} />
    </span>
    <div>
      <div className="activity-history-meta"><strong>{title}</strong>
        <time dateTime={item.occurredAt} title={fmt.shortDateTime(item.occurredAt)}>{fmt.time(item.occurredAt)}</time>
      </div>
      <div className="activity-history-reason"><b>{item.reason?.name ?? t("transfers.from_queue")}</b>
        {item.kind === "TRANSFER" && item.reason?.isActive === false && <small>{t("transfers.reason_disabled")}</small>}
        {item.kind === "TRANSFER" && item.reason?.currentName !== item.reason?.name && <small>{t("transfers.reason_renamed")}</small>}
      </div>
      {item.comment && <p>{item.comment}</p>}
    </div>
  </article>;
}
