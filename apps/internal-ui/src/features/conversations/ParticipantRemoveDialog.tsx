import { useState } from "react";
import { Modal } from "antd";
import { Button } from "../../shared/ui-controls";
import { t } from "../../i18n";
import type { ApiParticipant } from "./participantApi";

export function ParticipantRemoveDialog({ row, busy, error, onCancel, onSubmit }: {
  row: ApiParticipant; busy: boolean; error: string; onCancel: () => void;
  onSubmit: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  return <Modal open title={t("participants.remove_title", { name: row.member.name })} width={460}
    className="participant-remove-dialog" onCancel={() => !busy && onCancel()} closable={false}
    footer={<><Button variant="secondary" disabled={busy} onClick={onCancel}>{t("common.cancel")}</Button>
      <Button variant="danger-outline" disabled={busy} onClick={() => onSubmit(reason)}>{t("participants.remove")}</Button></>}>
    <p>{t("participants.remove_text", { name: row.member.name })}</p>
    {error && <div className="participant-banner" role="alert">{error}</div>}
    <label className="participant-reason-label">{t("participants.leave_reason")}
      <textarea value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} />
    </label><small className="participant-help">{t("participants.private_reason")}</small>
  </Modal>;
}
