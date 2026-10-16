import { useState } from "react";
import { Icon } from "../../shared/icons";
import { fmt, t, tn } from "../../i18n";
import { SmallAvatar } from "./assigneeOptions";
import { WorkStatusLabel } from "../work-status/WorkStatusLabel";
import { useParticipants } from "./useParticipants";
import { ParticipantAddForm } from "./ParticipantAddForm";
import { ParticipantRemoveDialog } from "./ParticipantRemoveDialog";
import type { ApiConversation } from "./apiTypes";
import type { ApiParticipant } from "./participantApi";
import "./participants.css";

export function ParticipantsSection({ detail, viewerId }: { detail: ApiConversation; viewerId: number | null }) {
  const model = useParticipants(detail);
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<ApiParticipant | null>(null);
  const canManage = detail.access?.actions.includes("conversations.participants") ?? false;
  const limit = model.roster?.additionalParticipantLimit;
  const full = limit != null && model.items.length >= limit;
  return <div className="participants-section" key={detail.id}>
    {model.error && <div className="participant-banner" role="alert">
      {model.failure && <strong>{t(model.failure.kind === "add" ? "participants.add_error" : "participants.remove_error", { name: model.failure.name })}</strong>}
      <span>{model.error}</span>
    </div>}
    <div className="participant-caption"><label>{t("participants.title")}</label>
      {limit != null && <small className={full ? "is-full" : ""}>{t("participants.count", { count: fmt.number(model.items.length), limit: fmt.number(limit) })}</small>}
    </div>
    <div className="participant-roster">
      {model.items.map((row) => <div className={`participant-row ${model.failure?.kind === "remove" && model.failure.id === row.id ? "is-error" : ""}`} key={row.id}>
        <SmallAvatar name={row.member.name} avatarUrl={row.member.avatarUrl} online={row.online} />
        <span className="participant-name">{row.member.name}{row.userId === viewerId ? t("common.you_suffix") : ""}</span>
        <WorkStatusLabel value={row.workStatus} />
        {canManage && <button type="button" disabled={model.busy} title={t("participants.remove")} aria-label={t("participants.remove_title", { name: row.member.name })} onClick={() => setRemoving(row)}><Icon name="close" size={12} /></button>}
      </div>)}
    </div>
    {canManage && <><button type="button" className="participant-add-button" disabled={full || model.busy || !model.roster}
      title={t(full ? "participants.limit_reached" : "participants.add")} onClick={() => setAdding(!adding)}><Icon name="plus" size={13} />{t("participants.add")}</button>
      {full && <p className="participant-help">{tn("participants.limit_note", limit!, { limit: fmt.number(limit!) })}</p>}
    </>}
    {adding && canManage && <ParticipantAddForm current={model.roster?.items ?? []} assigneeId={detail.assignedOperatorId} busy={model.busy} failed={model.failure?.kind === "add"}
      onCancel={() => setAdding(false)} onSubmit={async (id, name, reason) => { const success = await model.add(id, name, reason); if (success) setAdding(false); return success; }} />}
    {removing && canManage && <ParticipantRemoveDialog row={removing} busy={model.busy} error={model.failure?.kind === "remove" ? model.error : ""}
      onCancel={() => setRemoving(null)} onSubmit={(reason) => { void model.remove(removing, reason).then((success) => { if (success) setRemoving(null); }); }} />}
  </div>;
}
