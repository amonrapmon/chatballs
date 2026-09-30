import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RealtimeMessage } from "../realtime/connection";
import { useConversationEvents } from "./useConversationEvents";

const handlers = vi.hoisted(() => new Map<string, (message: RealtimeMessage) => void>());
vi.mock("../realtime/RealtimeProvider", () => ({
  useRealtime: () => ({ connected: true, watch: vi.fn() }),
  useRealtimeEvent: (type: string, handler: (message: RealtimeMessage) => void) => handlers.set(type, handler),
}));

describe("useConversationEvents", () => {
  beforeEach(() => handlers.clear());

  it("обновляет карточку и ленту открытого диалога после изменения полей сайта", () => {
    const refreshCard = vi.fn();
    const catchUp = vi.fn();
    const refreshInbox = vi.fn();
    function Workspace() {
      useConversationEvents({
        conversationId: 42,
        onInboxChanged: refreshInbox,
        onConversationChanged: (id) => { refreshCard(id); catchUp(); },
      });
      return null;
    }
    renderToStaticMarkup(<Workspace />);
    handlers.get("conversation.changed")!({ type: "conversation.changed", conversationId: 42 });
    expect(refreshCard).toHaveBeenCalledWith(42);
    expect(catchUp).toHaveBeenCalledOnce();
    handlers.get("conversation.changed")!({ type: "conversation.changed", conversationId: 99 });
    handlers.get("conversation.changed")!({ type: "conversation.changed", conversationId: "42" as unknown as number });
    expect(refreshCard).toHaveBeenCalledOnce();
    handlers.get("inbox.changed")!({ type: "inbox.changed" });
    expect(refreshInbox).toHaveBeenCalledOnce();
  });
});
