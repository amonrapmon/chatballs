import { Modal, Select } from "antd";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { useMediaQuery } from "../../shared/useMediaQuery";
import { Button } from "../../shared/ui-controls";
import type { ApiConversation } from "../conversations/model";
import { TransferRecipients } from "./TransferRecipients";
import { useTransferDialog } from "./useTransferDialog";
import "./styles.css";

export function TransferDialog({ detail, retainsReplyAfterTransfer, onUpdated, onClose, onTransferred }: {
  detail: ApiConversation; onUpdated: (next: ApiConversation) => void; onClose: () => void; onTransferred: (name: string) => void;
  retainsReplyAfterTransfer: boolean;
}) {
  const state = useTransferDialog(detail, onUpdated, onTransferred);
  const mobile = useMediaQuery("(max-width: 600px)");
  const disabled = state.busy || state.conflict;
  const recipientName = state.people.find((person) => person.id === state.recipient)?.name ?? "";
  const footer = <footer><small>{state.conflict ? t("transfers.not_transferred") : state.recipient
    ? t(retainsReplyAfterTransfer ? "transfers.next_assignee" : "transfers.future_assignee", { name: recipientName })
    : t("transfers.select_recipient_reason")}</small>
    {!mobile && <Button variant="secondary" disabled={state.busy} onClick={onClose}>{t("common.cancel")}</Button>}
    <Button variant="primary" icon={mobile ? undefined : state.busy ? "refresh" : "transfer"} disabled={disabled || !state.recipient || state.loading} onClick={() => void state.submit()}>{state.busy ? t("transfers.sending") : mobile && state.recipient ? t("transfers.mobile_submit", { name: recipientName }) : t("transfers.action")}</Button>
  </footer>;
  return <Modal open width={600} footer={footer} closable={!state.busy} maskClosable={false}
    onCancel={() => { if (!state.busy) onClose(); }} className="transfer-dialog"
    title={<>{mobile && <div className="transfer-sheet-handle" aria-hidden="true"><i /></div>}<h3>{t("transfers.dialog_title")}</h3>{!mobile && <p>{detail.contact?.name}</p>}</>}>
    {(state.error || state.unavailableName) && <div className={`transfer-banner ${state.conflict ? "is-warning" : "is-error"}`} role="alert">
      <Icon name={state.conflict ? "warning" : "errorCircle"} size={16} />
      <div><strong>{state.conflict ? t("transfers.conflict_title", { name: detail.assignedOperator?.name ?? t("conversations.not_set") })
        : state.unavailableName ? t("transfers.recipient_unavailable", { name: state.unavailableName }) : t("transfers.failed")}</strong>
        <p>{state.error || t("transfers.status_forbidden")}</p>
        {state.conflict && <div className="transfer-banner-actions">
          <Button variant="secondary" onClick={onClose}>{t("transfers.open_dialog")}</Button>
          <Button variant="secondary" onClick={onClose}>{t("common.close")}</Button>
        </div>}
      </div>
    </div>}
    <div className={`transfer-form ${disabled ? "is-muted" : ""}`}>
      <TransferRecipients people={state.people} recipient={state.recipient} query={state.query} onQuery={state.setQuery} onChoose={state.choose} disabled={disabled} />
      <label className="transfer-field"><span>{t("transfers.reason")}</span>
        <Select aria-label={t("transfers.reason")} placeholder={t("transfers.select_reason")} value={state.reason} disabled={disabled}
          status={state.reasonError ? "error" : undefined} onChange={state.selectReason}
          options={state.reasons.map((reason) => ({ value: reason.id, label: reason.name }))} />
        {state.reasonError && <small className="transfer-error">{state.reasonError}</small>}
      </label>
      <label className="transfer-field"><span>{t("transfers.comment")} {!mobile && <small>{t("transfers.optional")}</small>}</span>
        <textarea value={state.comment} disabled={disabled} placeholder={t(mobile ? "transfers.mobile_comment_placeholder" : "transfers.comment_placeholder")} onChange={(e) => state.setComment(e.target.value)} />
        <small className="transfer-private-note">{!mobile && <Icon name="lock" size={12} />}{t(mobile ? "transfers.mobile_private_note" : "transfers.private_note")}</small>
      </label>
    </div>
  </Modal>;
}
