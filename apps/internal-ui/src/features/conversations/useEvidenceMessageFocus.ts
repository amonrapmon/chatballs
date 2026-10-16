import { useEffect, useRef } from "react";
import type { ConversationFeed } from "./useConversationFeed";

/** Open an existing public message through the normal, authorized history feed. */
export function useEvidenceMessageFocus(conversationId: number | null, feed: ConversationFeed) {
  const focused = useRef(false);
  useEffect(() => {
    const requestedConversation = Number(new URLSearchParams(window.location.search).get("conversation"));
    const match = window.location.hash.match(/^#message-(\d+)$/);
    if (!match || requestedConversation !== conversationId || !feed.loaded || focused.current) return;
    const node = document.getElementById(`message-${match[1]}`)?.firstElementChild;
    if (node) { node.scrollIntoView({ block: "center" }); focused.current = true; }
    else if (feed.hasOlder && !feed.loadingOlder && !feed.errorText) feed.loadOlder();
  }, [conversationId, feed]);
}
