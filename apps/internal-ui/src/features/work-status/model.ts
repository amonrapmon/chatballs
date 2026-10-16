import { api } from "../../api/client";
import { fmt, t } from "../../i18n";

// Рабочий статус сотрудника в организации (макет «Расширение платформы»,
// кадры S1–S5, K2, E1). Статус хранит сервер и меняет только сам сотрудник;
// присутствие («приложение открыто») — отдельный признак и на статус не влияет.

export const workStatusCodes = ["READY", "BUSY", "BREAK", "UNAVAILABLE"] as const;
export type WorkStatusCode = typeof workStatusCodes[number];
/** До первого явного выбора сервер отдаёт UNAVAILABLE с версией 0 и без времени. */
export type WorkStatus = { status: WorkStatusCode; version: number; changedAt: string | null };
export type WorkStatusTransition = { status: WorkStatusCode; expectedVersion: number; operationId: string };

export const WORK_STATUS_EVENT = "work_status.changed";

export const fetchOwnWorkStatus = () => api<WorkStatus>("/api/v1/employees/me/work-status/");
export const saveWorkStatus = (transition: WorkStatusTransition) => api<WorkStatus>(
  "/api/v1/employees/me/work-status/",
  { method: "POST", body: JSON.stringify(transition) },
);

// Иконки lucide и цвета — из макета: circle-check, circle-minus, coffee, moon.
const presentation = {
  READY: { key: "ready", color: "var(--success-text)", stroke: "#52c41a", path: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM9 12l2 2 4-4" },
  BUSY: { key: "busy", color: "var(--error-text)", stroke: "#ff4d4f", path: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM8 12h8" },
  BREAK: { key: "break", color: "var(--warning-text)", stroke: "#faad14", path: "M10 2v2M14 2v2M6 2v2M16 8a1 1 0 0 1 1 1v8a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1h14a4 4 0 1 1 0 8h-1" },
  UNAVAILABLE: { key: "unavailable", color: "var(--n-4)", stroke: "#8c8c8c", path: "M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" },
} as const;

export function statusPresentation(code: WorkStatusCode) {
  return presentation[code];
}

/** «Готов принимать»; короткая форма — «Готов» (у остальных статусов она совпадает с полной). */
export function statusLabel(code: WorkStatusCode, short = false) {
  return t(short && code === "READY" ? "work_status.ready_short" : `work_status.${presentation[code].key}`);
}

export function statusDescription(code: WorkStatusCode) {
  return t(`work_status.${presentation[code].key}_description`);
}

function dayOf(date: Date, now: Date): "today" | "yesterday" | "earlier" {
  if (date.toDateString() === now.toDateString()) return "today";
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  return date.toDateString() === yesterday.toDateString() ? "yesterday" : "earlier";
}

/** «с 09:12» · «с вчера, 18:00» · «с 8 окт., 18:00». Без сохранённого времени — пусто. */
export function statusSince(value: string | null, now = new Date()): string {
  if (!value) return "";
  const date = new Date(value);
  const time = fmt.time(date);
  const day = dayOf(date, now);
  if (day === "today") return t("work_status.since", { time });
  if (day === "yesterday") return t("work_status.since", { time: t("time.yesterday_comma", { time }) });
  return t("work_status.since", { time: fmt.shortDateTime(date) });
}

/** Подвал меню: «Изменён сегодня в 09:12.» Без сохранённого времени — пусто. */
export function statusChangedNote(value: string | null, now = new Date()): string {
  if (!value) return "";
  const date = new Date(value);
  const time = fmt.time(date);
  const day = dayOf(date, now);
  if (day === "today") return t("work_status.changed_today", { time });
  if (day === "yesterday") return t("work_status.changed_yesterday", { time });
  return t("work_status.changed", { time: fmt.shortDateTime(date) });
}

// Справочник (кадр E1) дописывает присутствие там, где оно расходится со
// статусом: «Перерыв · в приложении», «Готов · приложение закрыто».
const WORKING: readonly WorkStatusCode[] = ["READY", "BUSY"];

export function presenceNote(code: WorkStatusCode, online: boolean): string {
  if (online === WORKING.includes(code)) return "";
  return t(online ? "work_status.in_app" : "work_status.app_closed_note");
}

// Запоздавший ответ или повтор операции не должен затирать более свежий снимок.
export function latestStatus(current: WorkStatus | null, incoming: WorkStatus): WorkStatus {
  return current && current.version > incoming.version ? current : incoming;
}
