import { api } from "../../api/client";

export type NotificationLevel = "INFO" | "SUCCESS" | "WARNING" | "CRITICAL";

export type AppNotification = {
  id: number;
  type: string;
  level: NotificationLevel;
  title: string;
  body: string;
  targetRoute: string;
  targetId: string;
  createdAt: string;
  unread: boolean;
};

export const LEVEL_META: Record<NotificationLevel, { color: string; icon: "bell" | "check" | "warning" | "xCircle" }> = {
  INFO: { color: "var(--primary)", icon: "bell" },
  SUCCESS: { color: "var(--success)", icon: "check" },
  WARNING: { color: "var(--warning)", icon: "warning" },
  CRITICAL: { color: "var(--error)", icon: "xCircle" },
};

export const fetchNotifications = () => api<{ items: AppNotification[]; unreadCount: number }>("/api/v1/notifications/");
export const markRead = (ids: number[]) => api("/api/v1/notifications/read/", { method: "POST", body: JSON.stringify({ ids }) });
export const markAllRead = () => api("/api/v1/notifications/read/", { method: "POST", body: JSON.stringify({ all: true }) });

export type NotificationTransport = "BROWSER" | "MESSENGER";

export type NotificationPreference = {
  transport: NotificationTransport;
  enabled: boolean;
  types: string[];
  availableTypes: Array<{ code: string; label: string }>;
};

export const fetchPreference = (transport: NotificationTransport) =>
  api<NotificationPreference>(`/api/v1/notifications/preferences/${transport}/`);

export const savePreference = (transport: NotificationTransport, patch: { enabled?: boolean; types?: string[] }) =>
  api<NotificationPreference>(`/api/v1/notifications/preferences/${transport}/`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
