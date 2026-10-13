import { Popover } from "antd";
import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { EmailAttemptJournal } from "./EmailAttemptJournal";
import { useEmailContinuation } from "./EmailContinuationContext";
import { emailReason, emailState, emailStatusIcons, emailStatusKeys, emailTone, startedAttempts } from "./emailStatus";
import type { EmailOperation } from "./emailTypes";

export function EmailMessageStatus({ operation }: { operation: EmailOperation }) {
  const mail = useEmailContinuation(), state = emailState(operation);
  const uncertain = operation.attempts.some((attempt) => attempt.state === "UNKNOWN");
  const reason = emailReason(operation, state);
  const note = state === "PENDING" ? t("mail.pending_note") : state === "SENDING" ? t("mail.sending_note") : state === "SMTP_ACCEPTED" ? t("mail.accepted_note")
    : state === "UNKNOWN" ? reason ? t("mail.unknown_reason_note", { reason }) : t("mail.unknown_note") : reason;
  return <div className="email-message-status">
    <b className={`email-status is-${emailTone[state]}`}><Icon name={emailStatusIcons[state]} size={11} />{t(emailStatusKeys[state])}</b>
    <small>{note}</small>
    {operation.retryAllowed && <button className="email-retry" type="button" disabled={mail?.busy} onClick={() => void mail?.retry(operation)}><Icon name="refresh" size={12} />{t(uncertain ? "mail.retry_unknown" : "mail.retry")}</button>}
    <Popover content={<EmailAttemptJournal operation={operation} />} trigger="click" placement="topRight" overlayClassName="email-journal-popover">
      <button className="link" type="button">{t("mail.attempts", { count: fmt.number(startedAttempts(operation)) })}</button>
    </Popover>
  </div>;
}
