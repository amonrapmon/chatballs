import { Icon } from "../../shared/icons";
import { t, tn } from "../../i18n";
import { SmallAvatar } from "./assigneeOptions";
import { waitLabelOf, type ApiConversation } from "./model";

// Блок «Ожидание» в карточке диалога (макет «Очередь и уведомления», кадр Q4).
//
// Отвечает на два вопроса, которые иначе оператору взять негде: сколько клиент
// уже ждёт человека и почему диалог виден, но брать его не нужно. Второе —
// единственное объяснение назначенному, но не взятому диалогу: без него он
// выглядит как обычный ждущий, который почему-то не даёт себя взять.

/** «через 3 минуты» — сколько осталось личной очереди. */
function leftFor(assignedAt: string, timeoutMinutes: number, now: Date): string | null {
  const deadline = new Date(assignedAt).getTime() + timeoutMinutes * 60000;
  const minutes = Math.round((deadline - now.getTime()) / 60000);
  return minutes > 0 ? tn("plural.minutes", minutes) : null;
}

export function WaitingBlock({
  detail,
  timeoutMinutes,
  now = new Date(),
}: {
  detail: ApiConversation;
  timeoutMinutes?: number;
  now?: Date;
}) {
  if (detail.lifecycle !== "OPEN" || detail.controlMode !== "PAUSED" || !detail.waitingSince) {
    return null;
  }
  const assignee = detail.assignedOperator;
  const left = assignee && detail.assignedAt && timeoutMinutes
    ? leftFor(detail.assignedAt, timeoutMinutes, now)
    : null;
  return (
    <div className="ctx-waiting">
      <div className="ctx-waiting-head">
        <Icon name="clock" size={15} strokeWidth={2} />
        <strong>{t("conversations.waiting_for_person", { duration: waitLabelOf(detail.waitingSince, now) })}</strong>
      </div>
      {assignee && (
        <>
          <div className="ctx-waiting-assignee">
            <SmallAvatar name={assignee.name} avatarUrl={assignee.avatarUrl} />
            <span>{t("conversations.assigned_not_taken", { name: assignee.name })}</span>
          </div>
          {left && <p>{t("conversations.returns_to_queue_in", { duration: left })}</p>}
        </>
      )}
    </div>
  );
}

