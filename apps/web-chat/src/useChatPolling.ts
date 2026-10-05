import { useEffect, type RefObject } from "react";
import { poll, SessionExpired, type Poll } from "./api";

export function useChatPolling(token: string | null, lastId: RefObject<number>, ready: RefObject<boolean>, ingest: (data: Poll, notify: boolean) => void, forget: () => void) {
  useEffect(() => {
    if (!token) return;
    let alive = true;
    const tick = async () => {
      try {
        const data = await poll(token, lastId.current);
        if (alive) {
          ingest(data, ready.current);
          ready.current = true;
        }
      } catch (error) {
        if (alive && error instanceof SessionExpired) forget();
        // Сеть или лимит: продолжаем опрашивать.
      }
    };
    void tick();
    const timer = setInterval(tick, 2500);
    return () => { alive = false; clearInterval(timer); };
  }, [token]);
}
