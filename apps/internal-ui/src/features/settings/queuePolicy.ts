import { api } from "../../api/client";
import { t } from "../../i18n";

// Сроки очереди (макет «Очередь и уведомления», кадр Q2). Четыре числа в
// минутах: через сколько напомнить группе, позвать всех, сообщить руководителю
// и сколько ждём назначенного сотрудника.

export type QueuePolicyField =
  | "remind_after_minutes"
  | "widen_after_minutes"
  | "escalate_after_minutes"
  | "assignment_timeout_minutes";

export type QueuePolicy = Record<QueuePolicyField, number> & {
  defaults: Record<QueuePolicyField, number>;
  updatedAt: string | null;
  updatedBy: string;
};

/** Порядок — как в макете: от первого напоминания к последнему средству. */
export const QUEUE_POLICY_FIELDS: Array<{ key: QueuePolicyField; title: string; hint: string }> = [
  {
    key: "remind_after_minutes",
    title: t("settings.queue_remind_group"),
    hint: t("settings.queue_remind_group_hint"),
  },
  {
    key: "widen_after_minutes",
    title: t("settings.queue_call_everyone"),
    hint: t("settings.queue_call_everyone_hint"),
  },
  {
    key: "escalate_after_minutes",
    title: t("settings.queue_tell_manager"),
    hint: t("settings.queue_tell_manager_hint"),
  },
  {
    key: "assignment_timeout_minutes",
    title: t("settings.queue_wait_for_assignee"),
    hint: t("settings.queue_wait_for_assignee_hint"),
  },
];

export const fetchQueuePolicy = () => api<QueuePolicy>("/api/v1/conversations/queue-policy/");

export const saveQueuePolicy = (patch: Partial<Record<QueuePolicyField, number>>) =>
  api<QueuePolicy>("/api/v1/conversations/queue-policy/", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
