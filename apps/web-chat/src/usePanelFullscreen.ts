import { useEffect, useState } from "react";

/**
 * Открыта ли панель на весь экран.
 *
 * Внутри iframe вьюпорт — это само окно виджета, и медиазапрос по ширине не
 * отличит телефон от обычной панели в 440px. Режим знает только лоадер: он
 * присылает `chatballs-chat-layout` после каждой раскладки. Первое такое
 * сообщение может прийти раньше, чем React повесит слушатель, поэтому после
 * монтирования панель сама спрашивает режим.
 */
export function usePanelFullscreen(): boolean {
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    function onParentMessage(event: MessageEvent) {
      if (event.source !== window.parent) return;
      const data = event.data as { type?: string; fullscreen?: unknown } | null;
      if (data?.type !== "chatballs-chat-layout") return;
      setFullscreen(Boolean(data.fullscreen));
    }
    window.addEventListener("message", onParentMessage);
    window.parent.postMessage({ type: "chatballs-chat-layout-request" }, "*");
    return () => window.removeEventListener("message", onParentMessage);
  }, []);

  return fullscreen;
}
