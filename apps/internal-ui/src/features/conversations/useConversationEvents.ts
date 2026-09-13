import { useEffect } from "react";

import { useRealtime, useRealtimeEvent } from "../realtime/RealtimeProvider";

// Оповещения о диалогах: сервер сообщает, что изменилось, клиент забирает
// данные обычным запросом. Поллинг остаётся запасным путём и замедляется, пока
// сокет жив, — при обрыве всё работает ровно как раньше.
//
// Сам сокет живёт в оболочке (features/realtime): он общий с уведомлениями и
// обязан работать на любом экране, а не только там, где открыт чат.

export type ConversationEvents = {
  /** Сокет открыт: поллинг можно замедлить. */
  connected: boolean;
};

export function useConversationEvents({
  conversationId,
  onInboxChanged,
  onConversationChanged,
}: {
  conversationId: number | null;
  onInboxChanged: () => void;
  onConversationChanged: (conversationId: number) => void;
}): ConversationEvents {
  const { connected, watch } = useRealtime();

  useRealtimeEvent("inbox.changed", () => onInboxChanged());
  useRealtimeEvent("conversation.changed", (message) => {
    if (typeof message.conversationId === "number") onConversationChanged(message.conversationId);
  });

  // Открытый диалог сообщается сокету заново и после переподключения: подписка
  // на него живёт в соединении, а не в реестре.
  useEffect(() => {
    watch(conversationId);
  }, [watch, conversationId, connected]);

  return { connected };
}
