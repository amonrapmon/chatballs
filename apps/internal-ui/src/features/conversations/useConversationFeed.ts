import { useCallback, useMemo } from "react";

import { fetchComments } from "./commentApi";
import { fetchMessages } from "./conversationApi";
import { conversationFeed, olderStream, type FeedRow } from "./feed";
import { useHistoryWindow } from "./useHistoryWindow";

export type ConversationFeed = {
  rows: FeedRow[];
  loaded: boolean;
  hasOlder: boolean;
  loadingOlder: boolean;
  errorText: string;
  loadOlder: () => void;
  /** Подтянуть новые сообщения переписки с клиентом. */
  catchUpMessages: () => Promise<void>;
  /** Подтянуть новые внутренние комментарии. */
  catchUpComments: () => Promise<void>;
};

/** Одна лента диалога из двух окон: сообщения и внутренние комментарии
 *  загружаются, догружаются и обновляются каждое своим запросом. */
export function useConversationFeed(
  conversationId: number | null,
  options: { live?: boolean; paused?: boolean } = {},
): ConversationFeed {
  const messages = useHistoryWindow(conversationId, fetchMessages, options);
  const comments = useHistoryWindow(conversationId, fetchComments, options);
  // Лента показывается, когда известны оба окна: иначе комментарии вклеились бы
  // в уже показанную переписку и сдвинули её. Сбой окна комментариев переписку
  // не прячет — о нём скажет строка ошибки.
  const loaded = messages.loaded && (comments.loaded || comments.errorText !== "");

  const rows = useMemo(
    () => (loaded
      ? conversationFeed({ items: messages.items, hasOlder: messages.hasOlder }, { items: comments.items, hasOlder: comments.hasOlder })
      : []),
    [loaded, messages.items, messages.hasOlder, comments.items, comments.hasOlder],
  );

  const loadOlderMessages = messages.loadOlder;
  const loadOlderComments = comments.loadOlder;
  const loadOlder = useCallback(() => {
    const stream = olderStream({ items: messages.items, hasOlder: messages.hasOlder }, { items: comments.items, hasOlder: comments.hasOlder });
    if (stream === "messages") loadOlderMessages();
    if (stream === "comments") loadOlderComments();
  }, [messages.items, messages.hasOlder, comments.items, comments.hasOlder, loadOlderMessages, loadOlderComments]);

  return {
    rows,
    loaded,
    hasOlder: messages.hasOlder || comments.hasOlder,
    loadingOlder: messages.loadingOlder || comments.loadingOlder,
    errorText: messages.errorText || comments.errorText,
    loadOlder,
    catchUpMessages: messages.catchUp,
    catchUpComments: comments.catchUp,
  };
}
