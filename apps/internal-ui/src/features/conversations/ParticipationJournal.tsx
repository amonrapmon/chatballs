import { useEffect, useState } from "react";
import { Modal, Pagination } from "antd";
import { Icon } from "../../shared/icons";
import { fmt, t } from "../../i18n";
import { fetchParticipationJournal, type JournalEntry, type JournalKind, type JournalPage } from "./participantApi";
import type { ApiConversation } from "./apiTypes";
import "./participants.css";

function JournalRows({ rows }: { rows: JournalEntry[] }) {
  return <>{rows.map((row) => <div className={`participation-journal-row is-${row.kind.toLowerCase()}`} key={row.id}>
    <span className="participation-journal-icon"><Icon name={row.kind === "TRANSFER" ? "transfer" : row.kind === "LEFT" ? "close" : "team"} size={13} /></span>
    <div className="participation-journal-content">
      <div><strong>{t(row.kind === "TRANSFER" ? "participants.transferred" : row.kind === "LEFT" ? "participants.left" : "participants.joined", { actor: row.actorName, subject: row.subjectName })}</strong><time>{fmt.shortDateTime(row.occurredAt)}</time></div>
      <div className="participation-journal-reason"><b>{row.reason}</b>
        {row.reasonInactive && <small>{t("participants.reason_inactive")}</small>}
        {row.reasonChanged && <small>{t("participants.reason_changed")}</small>}
      </div>{row.comment && <p>{row.comment}</p>}
    </div>
  </div>)}</>;
}

export function ParticipationJournal({ detail }: { detail: ApiConversation }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<JournalKind>("all");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<JournalPage | null>(null);
  const [preview, setPreview] = useState<JournalEntry[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetchParticipationJournal(detail.id, "all", 1, 3).then((value) => { if (active) setPreview(value.items); })
      .catch((problem) => { if (active) setError(problem instanceof Error ? problem.message : t("common.request_failed")); });
    return () => { active = false; };
  }, [detail]);
  useEffect(() => {
    if (!open) return;
    let active = true;
    setData(null); setError("");
    fetchParticipationJournal(detail.id, kind, page).then((value) => { if (active) setData(value); })
      .catch((problem) => { if (active) setError(problem instanceof Error ? problem.message : t("common.request_failed")); });
    return () => { active = false; };
  }, [detail, open, kind, page]);
  return <section className="ctx-section participation-journal">
    <div className="ctx-section-head"><h4>{t("participants.transfers")}</h4>
      <button type="button" className="link is-muted" onClick={() => setOpen(true)}>{t("participants.history")}</button></div>
    {error && !open && <p className="ctx-error" role="alert">{error}</p>}
    <JournalRows rows={preview} />
    <Modal open={open} onCancel={() => setOpen(false)} title={null} footer={null} width={420} className="participation-journal-modal" destroyOnHidden>
      <header><strong>{t("participants.journal_title")}</strong>
        <div role="tablist">{(["all", "transfers", "participants"] as const).map((tab) => <button type="button" role="tab" aria-selected={kind === tab} key={tab}
          onClick={() => { setKind(tab); setPage(1); }}>{t(tab === "participants" ? "participants.title" : tab === "transfers" ? "participants.transfers" : "participants.all")}</button>)}</div>
      </header>{error && <p className="ctx-error" role="alert">{error}</p>}
      <JournalRows rows={data?.items ?? []} />
      {data && data.pageCount > 1 && <Pagination current={data.page} total={data.total} pageSize={data.pageSize} showSizeChanger={false} onChange={setPage} />}
    </Modal>
  </section>;
}
