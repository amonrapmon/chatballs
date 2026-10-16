import { useEffect, useRef } from "react";

import { useRealtime, useRealtimeEvent } from "../realtime/RealtimeProvider";
import { WORK_STATUS_EVENT } from "./model";

// Обновление чужих статусов и присутствия в справочниках. Событие не несёт
// данных — только сигнал перечитать список по действующим правам. Присутствие
// событий не шлёт, поэтому список ещё и перечитывается по таймеру.

const POLL_CONNECTED_MS = 60_000;
const POLL_OFFLINE_MS = 15_000;

export function useAvailabilityRefresh(refresh: () => void | Promise<void>) {
  const { connected } = useRealtime();
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  const wasConnected = useRef(connected);

  useRealtimeEvent(WORK_STATUS_EVENT, () => void refreshRef.current());

  useEffect(() => {
    // После обрыва события потеряны — перечитываем сразу при восстановлении.
    if (connected && !wasConnected.current) void refreshRef.current();
    wasConnected.current = connected;
    const timer = setInterval(() => void refreshRef.current(), connected ? POLL_CONNECTED_MS : POLL_OFFLINE_MS);
    return () => clearInterval(timer);
  }, [connected]);
}
