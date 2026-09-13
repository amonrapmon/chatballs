import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { resolveWebSocketUrl } from "../../api/client";
import { RealtimeConnection } from "./connection";
import { RealtimeSubscribers, type RealtimeHandler } from "./subscribers";

// Сокет живёт на уровне оболочки, а не страницы чата. Раньше он принадлежал
// рабочей области диалогов, и вне чата живых событий не было вовсе: на любом
// другом экране оператор узнавал о новом уведомлении только следующим опросом.

type Realtime = {
  connected: boolean;
  subscribe: (type: string, handler: RealtimeHandler) => () => void;
  watch: (conversationId: number | null) => void;
};

const RealtimeContext = createContext<Realtime | null>(null);

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false);
  // Реестр создаётся раз и навсегда: подписки оформляются раньше, чем откроется
  // сокет, и переживают его переподключения.
  const subscribersRef = useRef<RealtimeSubscribers | null>(null);
  if (subscribersRef.current === null) subscribersRef.current = new RealtimeSubscribers();
  const subscribers = subscribersRef.current;
  const connectionRef = useRef<RealtimeConnection | null>(null);

  useEffect(() => {
    const url = resolveWebSocketUrl("/conversations/");
    if (!url) return;
    const connection = new RealtimeConnection(url, (message) => subscribers.dispatch(message), setConnected);
    connectionRef.current = connection;
    connection.open();
    return () => {
      connection.close();
      connectionRef.current = null;
      setConnected(false);
    };
  }, [subscribers]);

  // subscribe и watch не зависят от состояния соединения: иначе каждый обрыв
  // переподписывал бы всех подписчиков заново.
  const subscribe = useCallback(
    (type: string, handler: RealtimeHandler) => subscribers.subscribe(type, handler),
    [subscribers],
  );
  const watch = useCallback((conversationId: number | null) => connectionRef.current?.watch(conversationId), []);
  const value = useMemo<Realtime>(
    () => ({ connected, subscribe, watch }),
    [connected, subscribe, watch],
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtime(): Realtime {
  const value = useContext(RealtimeContext);
  if (value === null) throw new Error("useRealtime is only available inside RealtimeProvider");
  return value;
}

/** Подписка на один тип события. Обработчик держится в ref: пересоздание
 *  функции на каждом рендере не должно переподписывать сокет. */
export function useRealtimeEvent(type: string, handler: RealtimeHandler): void {
  const { subscribe } = useRealtime();
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  useEffect(() => subscribe(type, (message) => handlerRef.current(message)), [subscribe, type]);
}
