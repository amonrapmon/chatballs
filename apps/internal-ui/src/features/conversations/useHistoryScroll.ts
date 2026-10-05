import { useCallback, useLayoutEffect, useRef, type RefObject } from "react";

import type { ApiMessage } from "./model";
import { HistoryScrollState } from "./historyScrollState";

export type HistoryScroll = {
  onScroll: () => void;
};

/** Прокрутка ленты истории: держит низ при новых сообщениях, подгружает старые
 *  при подходе к верху и сохраняет место чтения, когда они вклеиваются сверху. */
export function useHistoryScroll(
  ref: RefObject<HTMLDivElement | null>,
  {
    conversationId,
    messages,
    viewerId,
    hasOlder,
    loadingOlder,
    loadOlder,
  }: {
    conversationId: number | null;
    messages: ApiMessage[];
    viewerId: number | null;
    hasOlder: boolean;
    loadingOlder: boolean;
    loadOlder: () => void;
  },
): HistoryScroll {
  const stateRef = useRef<HistoryScrollState | null>(null);
  if (stateRef.current === null) stateRef.current = new HistoryScrollState();

  useLayoutEffect(() => {
    const node = ref.current;
    if (node) stateRef.current!.update(node, { conversationId, messages, viewerId, loadingOlder });
  }, [conversationId, messages, viewerId, loadingOlder, ref]);

  const onScroll = useCallback(() => {
    const node = ref.current;
    if (node && stateRef.current!.onScroll(node, { hasOlder, loadingOlder })) loadOlder();
  }, [hasOlder, loadOlder, loadingOlder, ref]);

  return { onScroll };
}
