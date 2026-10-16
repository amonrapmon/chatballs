import { Dropdown } from "antd";
import { useEffect, useState, type ReactNode } from "react";

import { Icon } from "../../shared/icons";
import { DialogLabels } from "./DialogLabels";
import { NoteSection } from "./DialogNoteSection";
import { DialogAssigneeField } from "./DialogAssigneeField";
import { WaitingBlock } from "./WaitingBlock";
import { ParticipantsSection } from "./ParticipantsSection";
import { ParticipationJournal } from "./ParticipationJournal";
import { DialogPriorityField } from "./DialogPriorityField";
import { useEmployeeDirectory } from "./useEmployeeDirectory";
import { statusFor } from "./data";
import {
  agentColorOf,
  controlModeOf,
  groupColorOf,
  setConversationAssignee,
  setConversationGroup,
  setConversationNote,
  setConversationPriority,
  type ApiConversation,
} from "./model";
import type { EmployeeGroupRef } from "../../types";
import { fmt, t } from "../../i18n";

// Блок «Диалог» контекст-панели (дизайн-базлайн v2, решение 5): Ответственный,
// Группа, Приоритет — полноширинные селекты; Агент и Режим — read-only в две
// колонки; Метки — чипы с «+ Добавить»; Начат. Заметка — отдельная жёлтая карточка.


export function DialogControls({
  detail,
  groups,
  applyConversation,
  viewerId = null,
  assignmentTimeoutMinutes,
  afterDialog,
}: {
  detail: ApiConversation;
  groups: Array<EmployeeGroupRef & { color?: string }>;
  applyConversation: (updated: ApiConversation) => void;
  viewerId?: number | null;
  /** Срок личной очереди из счётчиков: по нему считается «вернётся через». */
  assignmentTimeoutMinutes?: number;
  afterDialog?: ReactNode;
}) {
  const directory = useEmployeeDirectory();
  const [busy, setBusy] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    setErrorText("");
  }, [detail.id]);

  async function run(action: () => Promise<ApiConversation>) {
    setBusy(true);
    setErrorText("");
    try {
      applyConversation(await action());
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : t("common.could_not_save"));
    } finally {
      setBusy(false);
    }
  }

  const assignee = detail.assignedOperator;
  const status = statusFor(detail.access?.isParticipant && !detail.isAssignedToViewer ? "assigned" : controlModeOf(detail), assignee?.name);
  const canEdit = detail.access?.actions.includes("conversations.assign") ?? false;
  const canOperate = detail.access?.actions.includes("conversations.operate") ?? false;

  return (
    <>
      <section className="ctx-section">
        <div className="ctx-section-head">
          <h4>{t("conversations.conversation")}</h4>
          <button type="button" aria-label={collapsed ? t("profile.expand") : t("conversations.collapse")} className={collapsed ? "is-collapsed" : ""} onClick={() => setCollapsed((value) => !value)}><Icon name="chevron" size={14} /></button>
        </div>
        {!collapsed && (
          <div className="ctx-fields">
            {errorText && <p className="ctx-error">{errorText}</p>}
            <WaitingBlock detail={detail} timeoutMinutes={assignmentTimeoutMinutes} />

            <DialogAssigneeField
              assignee={assignee} directory={directory} viewerId={viewerId} busy={busy} canEdit={canEdit}
              onPick={(id) => void run(() => setConversationAssignee(detail.id, id))}
            />

            {detail.access?.supervised && <p className="supervision-control-note">{t("supervision.control_hint", { group: detail.group?.name ?? "" })}</p>}
            <ParticipantsSection key={detail.id} detail={detail} viewerId={viewerId} />

            <label className="ctx-label">{t("common.group")}</label>
            <Dropdown
              disabled={!canEdit || busy || groups.length === 0}
              trigger={["click"]}
              overlayClassName="app-dropdown ctx-menu"
              menu={{
                // Кадр G: заголовок «Перенести в группу», отмеченный пункт с галочкой, подпись внизу.
                items: [
                  { key: "title", type: "group" as const, label: t("conversations.move_group") },
                  { key: "none", label: <button type="button" className={detail.group ? "" : "is-checked"} onClick={() => void run(() => setConversationGroup(detail.id, null))}><i className="ctx-dot is-muted" /><span>{t("common.no_group")}</span>{!detail.group && <Icon name="check" size={15} />}</button> },
                  ...groups.map((group) => ({
                    key: group.id,
                    label: <button type="button" className={detail.group?.id === group.id ? "is-checked" : ""} onClick={() => void run(() => setConversationGroup(detail.id, group.id))}><i className="ctx-dot" style={{ background: groupColorOf(group.id, group.color) }} /><span>{group.name}</span>{detail.group?.id === group.id && <Icon name="check" size={15} />}</button>,
                  })),
                  { key: "note", type: "group" as const, className: "ctx-menu-note", label: t("conversations.conversation_without_group_visible_every") },
                ],
              }}
            >
              <button type="button" className="ctx-select">
                <i className={`ctx-dot ${detail.group ? "" : "is-muted"}`} style={detail.group ? { background: groupColorOf(detail.group.id, detail.group.color) } : undefined} />
                <span>{detail.group?.name ?? t("common.no_group")}</span>
                {canEdit && <Icon name="chevron" size={14} />}
              </button>
            </Dropdown>

            <DialogPriorityField priority={detail.priority} busy={busy || !canOperate} onPick={(value) => void run(() => setConversationPriority(detail.id, value))} />

            <div className="ctx-grid">
              {detail.hasAgent !== false && <div>
                <label className="ctx-label">{t("common.agent")}</label>
                <div className="ctx-readonly" style={{ color: agentColorOf(detail.channel.id) }}><Icon name="robot" size={14} />{detail.channel.name}</div>
              </div>}
              <div>
                <label className="ctx-label">{t("conversations.mode")}</label>
                <div className="ctx-readonly is-mode" style={{ color: status.color, background: status.bg, borderColor: status.border }}><i style={{ background: status.dot }} />{status.label}</div>
              </div>
            </div>

            <DialogLabels detail={detail} busy={busy} setBusy={setBusy} setErrorText={setErrorText} applyConversation={applyConversation} run={run} />

            <div className="ctx-meta-row">
              <span>{detail.waitingSince ? t("conversations.in_queue_since") : t("conversations.started")}</span>
              <span>{startedLabel(detail.waitingSince ?? detail.createdAt)}</span>
            </div>
          </div>
        )}
      </section>

      <ParticipationJournal key={detail.id} detail={detail} />
      {afterDialog}
      <NoteSection detail={detail} busy={busy} onSave={(note) => run(() => setConversationNote(detail.id, note))} />
    </>
  );
}

// «сегодня, 17:02» · «вчера, 11:05» · «12 авг, 09:30»
export function startedLabel(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const time = fmt.time(date);
  if (date.toDateString() === now.toDateString()) return t("time.today_comma", { time });
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return t("time.yesterday_comma", { time });
  return fmt.shortDateTime(date);
}

