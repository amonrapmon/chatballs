import { t, tn } from "../../i18n";
import { WorkStatusBadge } from "./WorkStatusBadge";
import { recipientPresence, TransferRecipientAvatar } from "./TransferRecipientPerson";
import type { TransferRecipientsProps } from "./TransferRecipients";

export function MobileTransferRecipients({ people, recipient, onChoose, disabled }: TransferRecipientsProps) {
  return <div className="mobile-transfer-recipients">
    <span className="transfer-field-label">{t("transfers.to")}</span>
    {[true, false].map((allowed) => <div key={String(allowed)}>
      <div className="transfer-recipient-group">{t(allowed ? "transfers.allowed" : "transfers.forbidden")}</div>
      {people.filter((person) => person.assignmentAllowed === allowed).map((person) =>
        <button type="button" key={person.id} className={`mobile-transfer-person ${recipient === person.id ? "is-selected" : ""}`}
          disabled={disabled || !allowed} aria-pressed={recipient === person.id} onClick={() => onChoose(person.id)}>
          <TransferRecipientAvatar person={person} />
          <span className="mobile-transfer-person-info">
            <strong>{person.name}</strong>
            <span><WorkStatusBadge status={person.workStatus.status} /><span>· {tn("transfers.dialog_count", person.openDialogs ?? 0)}</span></span>
            <small>{recipientPresence(person)}</small>
          </span>
          <i className="transfer-radio" aria-hidden="true">{recipient === person.id && <b />}</i>
        </button>)}
    </div>)}
  </div>;
}
