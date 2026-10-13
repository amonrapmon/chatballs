import { fmt, t } from "../../i18n";
import type { EmailOperation } from "./emailTypes";
import { emailStatusKeys, emailTone } from "./emailStatus";

export function EmailAttemptJournal({ operation }: { operation: EmailOperation }) {
  return <div className="email-attempt-journal">
    <header><strong>{t("mail.attempts_title")}</strong><small>{operation.subject} · {operation.recipient}</small></header>
    {[...operation.attempts].sort((a, b) => b.number - a.number).map((attempt) => <div className="email-attempt-row" key={attempt.id}>
      <span>{fmt.number(attempt.number)}</span><div><b className={`email-status is-${emailTone[attempt.state]}`}>{t(emailStatusKeys[attempt.state])}</b>
        {attempt.number > 1 && <small>{t("mail.repeat_actor", { name: attempt.initiatedByName })}</small>}
        {attempt.errorMessage && <small>{attempt.errorMessage}</small>}
      </div><time title={fmt.shortDateTime(attempt.finishedAt || attempt.startedAt || attempt.createdAt)} dateTime={attempt.finishedAt || attempt.startedAt || attempt.createdAt}>{fmt.time(attempt.finishedAt || attempt.startedAt || attempt.createdAt)}</time>
    </div>)}
    <footer>{t("mail.journal_note")}</footer>
  </div>;
}
