import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { useRealtime, useRealtimeEvent } from "../realtime/RealtimeProvider";
import { fetchOwnWorkStatus, latestStatus, saveWorkStatus, WORK_STATUS_EVENT, type WorkStatus, type WorkStatusCode, type WorkStatusTransition } from "./model";

// Собственный рабочий статус в текущей организации. Источник истины — сервер:
// `saved` всегда пришёл оттуда, выбранное значение живёт в `pending` только
// пока идёт запрос. Потеря связи статус не трогает (SPEC-0028, R-3).

const POLL_CONNECTED_MS = 60_000;
const POLL_OFFLINE_MS = 15_000;
// Короткий обрыв и первое подключение при загрузке — ещё не «нет связи».
const CONNECTION_LOST_AFTER_MS = 3_000;

function useConnectionLost(connected: boolean): boolean {
  const [lost, setLost] = useState(false);
  useEffect(() => {
    if (connected) {
      setLost(false);
      return;
    }
    const timer = setTimeout(() => setLost(true), CONNECTION_LOST_AFTER_MS);
    return () => clearTimeout(timer);
  }, [connected]);
  return lost;
}

export function useOwnWorkStatus() {
  const [saved, setSaved] = useState<WorkStatus | null>(null);
  const [pending, setPending] = useState<WorkStatusTransition | null>(null);
  const [failed, setFailed] = useState<WorkStatusTransition | null>(null);
  const inFlight = useRef(false);
  const alive = useRef(true);
  const { connected } = useRealtime();
  const connectionLost = useConnectionLost(connected);

  const refresh = useCallback(async (): Promise<WorkStatus | null> => {
    try {
      const value = await fetchOwnWorkStatus();
      if (alive.current) setSaved((current) => latestStatus(current, value));
      return value;
    } catch {
      // Связи нет: на экране остаётся последний сохранённый статус.
      return null;
    }
  }, []);

  // Переподключение перечитывает статус сразу: события за время обрыва потеряны.
  useEffect(() => {
    alive.current = true;
    void refresh();
    const timer = setInterval(() => void refresh(), connected ? POLL_CONNECTED_MS : POLL_OFFLINE_MS);
    return () => {
      alive.current = false;
      clearInterval(timer);
    };
  }, [refresh, connected]);
  // Событие — только сигнал: актуальное значение читается с сервера по правам.
  useRealtimeEvent(WORK_STATUS_EVENT, () => void refresh());

  async function submit(transition: WorkStatusTransition) {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(transition);
    setFailed(null);
    try {
      const value = await saveWorkStatus(transition);
      if (alive.current) setSaved((current) => latestStatus(current, value));
      // Повтор операции возвращает её исходный результат — сверяемся с текущим.
      await refresh();
    } catch (error) {
      const current = await refresh();
      // Ответ мог потеряться уже после сохранения: тогда ошибки нет.
      if (alive.current && current?.status !== transition.status) {
        // Версия устарела — повтор пойдёт новой операцией; иначе — той же.
        const stale = error instanceof ApiError && error.status === 409;
        setFailed(stale ? { ...transition, operationId: "" } : transition);
      }
    } finally {
      inFlight.current = false;
      if (alive.current) setPending(null);
    }
  }

  function choose(status: WorkStatusCode) {
    if (!saved || inFlight.current || status === saved.status) return;
    void submit({ status, expectedVersion: saved.version, operationId: crypto.randomUUID() });
  }

  function retry() {
    if (!failed || !saved) return;
    void submit(failed.operationId ? failed : { status: failed.status, expectedVersion: saved.version, operationId: crypto.randomUUID() });
  }

  return {
    saved,
    pending,
    // Статус мог смениться в другой вкладке: ошибка о нём больше не актуальна.
    failed: failed && saved?.status !== failed.status ? failed : null,
    choose,
    retry,
    online: !connectionLost,
    connectionLost,
  };
}

export type OwnWorkStatus = ReturnType<typeof useOwnWorkStatus>;
