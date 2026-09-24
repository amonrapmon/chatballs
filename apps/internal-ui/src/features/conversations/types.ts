// Общие типы workspace диалогов (sales + support):
// общий conversation workspace, не отдельная реализация под каждый отдел.

export type DialogMode = "ai" | "closed" | "operator" | "wait";
export type ControlMode = "ai" | "assigned" | "closed" | "human" | "waiting";
// Два ожидания — разные списки (макет «Очередь и уведомления», кадр Q3):
// «queue» — диалоги без ответственного, взять может любой; «onMe» —
// назначенные лично и ждущие, пока их возьмут.
export type ListTab = "all" | "mine" | "queue" | "onMe";
// Порядок инбокса. Считает его сервер: список приходит окном, и сортировать в
// браузере было бы нечего.
export type ListSort = "activity" | "waiting";
export type ChannelKey = "EMAIL" | "MAX" | "TG" | "VK" | "WEB";

// Элемент списка диалогов (бывш. SalesDialog). Полностью generic.
export type ConversationListItem = {
  id: number;
  name: string;
  initials: string;
  avatarBg: string;
  avatarUrl?: string;
  channel: ChannelKey;
  email: string;
  mode: DialogMode;
  preview: string;
  time: string;
  unread: number;
  // Дизайн-базлайн v2: вкладка «Мои», приоритет и бейджи строки.
  isMine: boolean;
  priority: "HIGH" | "MEDIUM" | "LOW" | "NONE";
  labels: Array<{ id: number; name: string; color: string }>;
  // Строка диалога (решение 4): агент в цвете, группа с точкой, таймер ожидания,
  // «↩» — последнее сообщение наше.
  agentName: string;
  agentColor: string;
  groupName: string | null;
  groupColor: string;
  waitLabel: string | null;
  /** «на вас · вернётся через 4 мин» — личная очередь (макет Q3). */
  mineLabel: string | null;
  lastIsOurs: boolean;
  // Последнее сообщение — голосовое: в превью иконка микрофона (макет).
  lastIsVoice: boolean;
};

export type StatusInfo = {
  label: string;
  color: string;
  bg: string;
  border: string;
  dot: string;
};
