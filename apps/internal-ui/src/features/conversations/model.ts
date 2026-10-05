import type { ChannelKey, ConversationListItem, ControlMode, DialogMode } from "./types";
import { fmt, t } from "../../i18n";

export * from "./apiTypes";
import { isImageAttachment } from "./apiTypes";
import type { ApiConversation } from "./apiTypes";

const AVATAR_PALETTE = ["#eb6f4b", "#3b82c4", "#9254de", "#13a8a8", "#d4860b", "#52a838", "#c4413b", "#6b5be0"];
// Цвет агента и цвет точки группы — стабильно из идентификатора. Палитра идёт
// по порядку создания агентов, как в дизайн-базлайне (решение 6a): первый
// агент «Консультант» — фиолетовый, второй «Поддержка сайта» — бирюзовый,
// четвёртый «Приёмная» — оранжевый. Хеш кода здесь не годился: он давал
// и другие цвета, и совпадения у разных агентов.
const AGENT_PALETTE = ["var(--ai)", "#0f9b8e", "#6d5dfc", "#e8590c", "#d4860b"];
const GROUP_PALETTE = ["var(--primary)", "#2aa876", "#e8590c", "#6d5dfc", "#d4860b"];

export function agentColorOf(agentId: number): string {
  return AGENT_PALETTE[(agentId - 1) % AGENT_PALETTE.length];
}

// Цвет группы — заданный в настройках (дизайн-базлайн v2), иначе палитра по id.
export function groupColorOf(groupId: number, color?: string | null): string {
  return color || GROUP_PALETTE[groupId % GROUP_PALETTE.length];
}

// Время в строке списка: сегодня — часы, вчера — «вчера», дальше — дата.
export function listTime(iso: string, now = new Date()): string {
  const date = new Date(iso);
  const sameDay = date.toDateString() === now.toDateString();
  if (sameDay) return fmt.time(date);
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return t("common.yesterday");
  return fmt.shortDate(date);
}

// Таймер ожидания оператора: «6 мин», «1 ч 50 мин» — без слова «ждёт» (решение 4).
export function waitLabelOf(sinceIso: string, now = new Date()): string {
  const minutes = Math.max(0, Math.round((now.getTime() - new Date(sinceIso).getTime()) / 60000));
  if (minutes < 60) return t("time.minutes_short", { count: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours >= 24) return t("time.days_short", { count: Math.floor(hours / 24) });
  const rest = minutes % 60;
  return rest ? t("time.hours_minutes", { hours, minutes: rest }) : t("time.hours_short", { count: hours });
}
const PROVIDER_CHANNEL: Record<string, ChannelKey> = {
  EMAIL: "EMAIL",
  MAX: "MAX",
  TELEGRAM: "TG",
  VK: "VK",
  WEB: "WEB",
};

export function controlModeOf(conversation: ApiConversation): ControlMode {
  if (conversation.lifecycle !== "OPEN") return "closed";
  if (conversation.controlMode === "HUMAN") {
    return conversation.isAssignedToViewer ? "human" : "assigned";
  }
  if (conversation.controlMode === "AI") return "ai";
  return "waiting";
}

function dialogMode(conversation: ApiConversation): DialogMode {
  if (conversation.lifecycle === "CLOSED") return "closed";
  if (conversation.controlMode === "HUMAN") return "operator";
  if (conversation.controlMode === "AI") return "ai";
  return "wait";
}

function formatPreviewDuration(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return t("conversations.g");
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

export function conversationName(conversation: ApiConversation): string {
  if (conversation.contact) return conversation.contact.name || t("conversations.guest_number", { id: conversation.contact.id });
  return t("conversations.guest");
}

/** «на вас · вернётся через 4 мин» — сколько осталось личной очереди. */
export function assignedToMeLabel(
  conversation: ApiConversation,
  { viewerId, timeoutMinutes }: { viewerId: number | null; timeoutMinutes?: number },
  now = new Date(),
): string | null {
  if (!conversation.isAssignedToViewer || conversation.controlMode !== "PAUSED") return null;
  if (viewerId == null || !conversation.assignedAt || !timeoutMinutes) return t("conversations.on_you");
  const deadline = new Date(conversation.assignedAt).getTime() + timeoutMinutes * 60000;
  const left = Math.round((deadline - now.getTime()) / 60000);
  return left > 0 ? t("conversations.on_you_returns_in", { count: left }) : t("conversations.on_you");
}

export function toConversationListItem(
  conversation: ApiConversation,
  options: { viewerId?: number | null; assignmentTimeoutMinutes?: number } = {},
): ConversationListItem {
  const name = conversationName(conversation);
  // avatarBg: стабильно из id контакта.
  const seed = conversation.contact?.id ?? conversation.id;
  return {
    id: conversation.id,
    name,
    initials: initialsOf(name),
    avatarBg: AVATAR_PALETTE[seed % AVATAR_PALETTE.length],
    avatarUrl: conversation.contact?.avatarUrl || undefined,
    channel: PROVIDER_CHANNEL[conversation.connection?.provider ?? "WEB"] ?? "WEB",
    email: conversation.contact?.email ?? "",
    mode: dialogMode(conversation),
    preview:
      conversation.lastMessage?.kind === "voice"
        ? t("conversations.voice_message_duration", { duration: formatPreviewDuration(conversation.lastMessage.durationSeconds ?? 0) })
        : conversation.lastMessage?.kind === "file"
          ? (isImageAttachment(conversation.lastMessage) ? t("common.photo") : t("conversations.file_named", { name: conversation.lastMessage.attachmentName || "" })) + (conversation.lastMessage.text ? ` · ${conversation.lastMessage.text.replace(/\s+/g, " ").slice(0, 60)}` : "")
          : conversation.lastMessage?.text.replace(/\s+/g, " ").slice(0, 80) ?? "—",
    time: listTime(conversation.lastActivityAt),
    unread: conversation.pendingCount ?? 0,
    isMine: conversation.isAssignedToViewer,
    priority: conversation.priority ?? "NONE",
    labels: conversation.labels ?? [],
    agentName: conversation.channel.name,
    agentColor: agentColorOf(conversation.channel.id),
    groupName: conversation.group?.name ?? null,
    groupColor: conversation.group ? groupColorOf(conversation.group.id, conversation.group.color) : "var(--n-5)",
    // Таймер считается с момента постановки в очередь: по последней активности
    // клиент, напомнивший о себе, «ждал» бы заново с нуля.
    waitLabel:
      conversation.lifecycle === "OPEN" && conversation.controlMode === "PAUSED"
        ? waitLabelOf(conversation.waitingSince ?? conversation.lastActivityAt)
        : null,
    mineLabel: assignedToMeLabel(conversation, {
      viewerId: options.viewerId ?? null,
      timeoutMinutes: options.assignmentTimeoutMinutes,
    }),
    lastIsOurs: conversation.lastMessage?.author === "OPERATOR" || conversation.lastMessage?.author === "AI",
    lastIsVoice: conversation.lastMessage?.kind === "voice",
  };
}

// Видимость inbox решает backend (ADR-CHATBALLS-0043): группы сотрудника + без группы
// + назначенные ему; владелец и админ видят всё. Фильтры — серверные.
export * from "./conversationApi";
