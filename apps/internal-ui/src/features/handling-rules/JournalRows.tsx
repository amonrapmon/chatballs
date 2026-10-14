import { fmt, t } from "../../i18n";
import { instantLabel, timeLabel } from "../support-reports/presentation";
import { displayStatus } from "./journalModel";
import { ruleName } from "./model";
import type { RuleExecution } from "./types";

function eventLabel(entry: RuleExecution): string {
  if (entry.rule.kind === "ASSIGNMENT_RETURN") return t("handling_rules.event_assignment");
  if (entry.rule.kind === "RECEIPT_CONFIRMATION") return t("handling_rules.event_people");
  return t("handling_rules.event_waiting");
}

export function JournalRows({ entries, names, timezone, openConversation }: {
  entries: RuleExecution[]; names: Record<number, string>; timezone: string; openConversation: (id: number) => void;
}) {
  const headings = ["rule_filter", "event", "planned", "finished", "to", "result", "why"] as const;
  return <div className="handling-journal-table-scroll"><table className="handling-journal-table">
    <thead><tr>{headings.map(key => <th key={key}>{t(`handling_rules.${key}`)}</th>)}</tr></thead>
    <tbody>{entries.map(entry => {
      const status = displayStatus(entry);
      const performedAt = entry.status === "EXECUTED" || entry.status === "FAILED" ? entry.finishedAt : null;
      const recipients = entry.rule.kind === "RECEIPT_CONFIRMATION" ? t("handling_rules.customer")
        : entry.rule.kind === "ASSIGNMENT_RETURN" ? t("handling_rules.queue")
          : entry.recipients.map(recipient => recipient.name || `#${fmt.number(recipient.userId)}`).join(", ") || "—";
      return <tr key={entry.id}>
        <td><strong>{ruleName(entry.rule.kind)}</strong><small>{t("handling_rules.version", { version: fmt.number(entry.rule.version) })}</small></td>
        <td><span title={instantLabel(entry.sourceEvent.occurredAt, timezone)}>{eventLabel(entry)}</span>
          <button className="link is-neutral" type="button" onClick={() => openConversation(entry.conversationId)} title={`#${entry.conversationId}`}>
            {names[entry.conversationId] || `#${entry.conversationId}`}
          </button></td>
        <td title={instantLabel(entry.scheduledFor, timezone)}>{timeLabel(entry.scheduledFor, timezone)}</td>
        <td title={performedAt ? instantLabel(performedAt, timezone) : undefined}>{performedAt ? timeLabel(performedAt, timezone) : "—"}</td>
        <td>{recipients}</td>
        <td><span className={`handling-journal-status is-${status.toLowerCase()}`}>{t(`handling_rules.status_${status}`)}</span></td>
        <td>{entry.reasonLabel || "—"}</td>
      </tr>;
    })}</tbody>
  </table></div>;
}
