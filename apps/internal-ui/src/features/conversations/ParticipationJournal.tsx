import { useEffect, useState } from "react";
import { ActivityHistoryDialog } from "../transfers/ActivityHistoryDialog";
import { Icon } from "../../shared/icons";
import { fmt, t } from "../../i18n";
import { fetchParticipationJournal, type JournalEntry } from "./participantApi";
import type { ApiConversation } from "./apiTypes";
import "./participants.css";

function JournalRows({ rows }: { rows: JournalEntry[] }) {
  return <>{rows.map((row) => <div className={`participation-journal-row is-${row.kind.toLowerCase()}`} key={row.id}>
    <span className="participation-journal-icon"><Icon name={row.kind === "TRANSFER" ? "transfer" : row.kind === "LEFT" ? "close" : "team"} size={13} /></span>
    <div className="participation-journal-content">
      <div><strong>{t(row.kind === "TRANSFER" ? "transfers.history_entry" : row.kind === "LEFT" ? "transfers.participant_leave_entry" : "transfers.participant_join_entry", { from: row.actorName, to: row.subjectName })}</strong><time>{fmt.shortDateTime(row.occurredAt)}</time></div>
      <div className="participation-journal-reason"><b>{row.reason}</b>
        {row.reasonInactive && <small>{t("participants.reason_inactive")}</small>}
        {row.reasonChanged && <small>{t("participants.reason_changed")}</small>}
      </div>{row.comment && <p>{row.comment}</p>}
    </div>
  </div>)}</>;
}

export function ParticipationJournal({ detail }: { detail: ApiConversation }) {
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<JournalEntry[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetchParticipationJournal(detail.id, "all", 1, 3).then((value) => { if (active) setPreview(value.items); })
      .catch((problem) => { if (active) setError(problem instanceof Error ? problem.message : t("common.request_failed")); });
    return () => { active = false; };
  }, [detail]);
  return <section className="ctx-section participation-journal">
    <div className="ctx-section-head"><h4>{t("participants.transfers")}</h4>
      <button type="button" className="link is-muted" onClick={() => setOpen(true)}>{t("participants.history")}</button></div>
    {error && !open && <p className="ctx-error" role="alert">{error}</p>}
    <JournalRows rows={preview} />
    {open && <ActivityHistoryDialog conversationId={detail.id} onClose={() => setOpen(false)} />}
  </section>;
}
