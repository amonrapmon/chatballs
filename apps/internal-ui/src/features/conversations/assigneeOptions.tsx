import type { ItemType } from "antd/es/menu/interface";

import { Icon } from "../../shared/icons";
import { SearchInput } from "../../shared/ui-controls";
import { t } from "../../i18n";
import type { ChatDirectoryEmployee } from "./model";
import type { EmployeeDirectory } from "./useEmployeeDirectory";

/** Инициалы: «Анна Ким» → «АК». */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
}

/** Маленький аватар строки выбора: используется и в списке, и в закрытом поле. */
export function SmallAvatar({ name, avatarUrl, online }: { name: string; avatarUrl?: string | null; online?: boolean }) {
  // Точка присутствия живёт внутри аватара: у него фиксированный размер, и
  // угол, к которому её прижимают, всегда там, где ожидается.
  const dot = online ? <i className="assignee-dot" /> : null;
  if (avatarUrl) {
    return <span className="ctx-avatar-small has-photo">{dot}<img src={avatarUrl} alt="" /></span>;
  }
  return <span className="ctx-avatar-small">{dot}{initials(name)}</span>;
}

// Выбор ответственного (макет «Очередь и уведомления», кадр Q5): сначала те,
// кто сейчас в приложении, потом остальные. Отсутствующих не скрываем и не
// блокируем — признак приблизительный, назначить можно любого; они просто не
// первыми попадаются на глаза.

/** «не в приложении · 25 мин» — сколько человека уже нет. */
export function awayFor(lastSeenAt: string | null | undefined, now = new Date()): string {
  if (!lastSeenAt) return t("conversations.never_in_app");
  const seen = new Date(lastSeenAt);
  if (Number.isNaN(seen.getTime())) return t("conversations.never_in_app");
  const minutes = Math.max(1, Math.round((now.getTime() - seen.getTime()) / 60000));
  if (minutes < 60) return t("conversations.away_minutes", { count: minutes });
  const hours = Math.round(minutes / 60);
  if (hours < 24) return t("conversations.away_hours", { count: hours });
  return t("conversations.away_long");
}

function subtitleOf(employee: ChatDirectoryEmployee): string {
  if (!employee.online) return awayFor(employee.lastSeenAt);
  return employee.role === "OWNER" ? t("conversations.here_owner") : t("conversations.here");
}

function personItem(
  employee: ChatDirectoryEmployee,
  { viewerId, assigneeId, onPick }: { viewerId: number | null; assigneeId?: number; onPick: (id: number) => void },
): ItemType {
  const load = employee.openDialogs ?? 0;
  return {
    key: employee.id,
    label: (
      <button
        type="button"
        className={`assignee-option ${assigneeId === employee.id ? "is-checked" : ""}`}
        onClick={() => onPick(employee.id)}
      >
        <SmallAvatar name={employee.name} avatarUrl={employee.avatarUrl} online={employee.online} />
        <span className="assignee-who">
          <span>{employee.name}{viewerId === employee.id ? t("common.you_suffix") : ""}</span>
          <small className={employee.online ? "is-here" : ""}>{subtitleOf(employee)}</small>
        </span>
        {load > 0 && <small className="assignee-load">{t("conversations.open_dialogs", { count: load })}</small>}
        {assigneeId === employee.id && <Icon name="check" size={15} />}
      </button>
    ),
  };
}

export function assigneeMenuItems({
  directory,
  viewerId,
  assigneeId,
  onPick,
}: {
  directory: EmployeeDirectory;
  viewerId: number | null;
  assigneeId?: number;
  onPick: (id: number | null) => void;
}): ItemType[] {
  const here = directory.employees.filter((employee) => employee.online);
  const away = directory.employees.filter((employee) => !employee.online);
  const pick = { viewerId, assigneeId, onPick: (id: number) => onPick(id) };
  return [
    // Строка поиска появляется, когда коллег больше, чем помещается в выдачу
    // справочника: маленькой команде она не нужна.
    ...(directory.hasMore || directory.query
      ? [{
        key: "search",
        type: "group" as const,
        label: (
          <SearchInput
            className="ctx-menu-search"
            placeholder={t("conversations.name_or_email")}
            value={directory.query}
            onChange={directory.setQuery}
          />
        ),
      }]
      : []),
    {
      key: "none",
      label: (
        <button type="button" className={assigneeId ? "" : "is-checked"} onClick={() => onPick(null)}>
          <span className="ctx-avatar-empty" />
          <span>{t("conversations.unassigned")}</span>
          {!assigneeId && <Icon name="check" size={15} />}
        </button>
      ),
    },
    ...(here.length > 0
      ? [{ key: "here-head", type: "group" as const, label: t("conversations.presence_here") }]
      : []),
    ...here.map((employee) => personItem(employee, pick)),
    ...(away.length > 0
      ? [{ key: "away-head", type: "group" as const, label: t("conversations.presence_away") }]
      : []),
    ...away.map((employee) => personItem(employee, pick)),
    {
      key: "presence-note",
      type: "group" as const,
      className: "ctx-menu-note",
      label: t("conversations.presence_note"),
    },
  ];
}
