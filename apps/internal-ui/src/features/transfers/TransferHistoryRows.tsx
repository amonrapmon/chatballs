import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import type { TransferRecord } from "./api";

export function TransferHistoryRows({ items }: { items: TransferRecord[] }) {
  return <>{items.map((row) => <article className="transfer-history-entry" key={row.id} data-operation-id={row.operationId}>
    <div className="transfer-history-names">
      <span>{row.initiatedBy?.name ?? t("conversations.not_set")}</span><Icon name="arrow" size={12} />
      <span>{row.newOperator?.name ?? t("conversations.not_set")}</span>
      <time dateTime={row.occurredAt} title={fmt.shortDateTime(row.occurredAt)}>{fmt.shortDateTime(row.occurredAt)}</time>
    </div>
    <div className="transfer-history-reason"><b>{row.reason.name}</b>
      {!row.reason.isActive && <small>{t("transfers.reason_disabled")}</small>}
      {row.reason.currentName !== row.reason.name && <small>{t("transfers.reason_renamed")}</small>}
    </div>
    {row.comment && <p><Icon name="lock" size={11} />{row.comment}</p>}
  </article>)}</>;
}
