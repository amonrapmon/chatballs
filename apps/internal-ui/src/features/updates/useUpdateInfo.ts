import { useCallback, useEffect, useRef, useState } from "react";

import { fetchUpdate, installInProgress, type UpdateInfo } from "./api";

// Состояние обновления с опросом, пока идёт установка.
//
// Обновление перезапускает тот самый бэкенд, который о нём и рассказывает, —
// поэтому «не отвечает» здесь не ошибка, а стадия. По той же причине признак
// «идёт установка» нельзя держать только в памяти вкладки: страница может
// перезагрузиться (руками или потому что человек ждёт) ровно тогда, когда
// сервисы лежат, и вернуться в интерфейс, где про обновление нет ни слова.
// Метка живёт в sessionStorage до подтверждения от поднявшейся версии.

const POLL_INTERVAL_MS = 3000;
const MARK_KEY = "chatballs.update.pending";
// Обновление занимает минуты; за час оно либо кончилось, либо не кончится уже
// никогда — забытая метка не должна вечно показывать мнимую установку.
const MARK_TTL_MS = 60 * 60 * 1000;

type Mark = { version: string | null; at: number };

function readMark(): Mark | null {
  try {
    const raw = sessionStorage.getItem(MARK_KEY);
    if (!raw) return null;
    const mark = JSON.parse(raw) as Mark;
    if (typeof mark?.at !== "number" || Date.now() - mark.at > MARK_TTL_MS) {
      sessionStorage.removeItem(MARK_KEY);
      return null;
    }
    return mark;
  } catch {
    return null;
  }
}

function writeMark(mark: Mark): void {
  try {
    sessionStorage.setItem(MARK_KEY, JSON.stringify(mark));
  } catch {
    /* приватное окно — переживём и без метки */
  }
}

function clearMark(): void {
  try {
    sessionStorage.removeItem(MARK_KEY);
  } catch {
    /* см. выше */
  }
}

export function useUpdateInfo(enabled: boolean) {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  // Метка переживает перезагрузку страницы, состояние — нет; нужны обе.
  const [pending, setPending] = useState<Mark | null>(() => readMark());
  // Версия, которую бэкенд назвал при загрузке этой страницы. Если она потом
  // изменилась — в браузере лежит код прошлой версии, и его надо перечитать.
  const loadedVersion = useRef<string | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await fetchUpdate();
      if (loadedVersion.current === null) loadedVersion.current = next.currentVersion;
      setInfo(next);
      setUnreachable(false);
    } catch {
      // Нет прав, сеть моргнула или бэкенд перезапускается — различить нельзя.
      setUnreachable(true);
    }
  }, []);

  useEffect(() => {
    if (enabled) void load();
  }, [enabled, load]);

  const running = installInProgress(info);
  // Пока бэкенд молчит, верим метке: молчит он как раз потому, что обновляется.
  const installing = running || (pending !== null && (unreachable || info === null));

  useEffect(() => {
    if (running && info) {
      // Начало берётся от сервера: после перезагрузки страницы бэкенд уже может
      // не отвечать, и счётчик времени иначе пошёл бы заново.
      const requested = Date.parse(info.install.requestedAt ?? "");
      const mark = { version: info.install.version, at: Number.isNaN(requested) ? Date.now() : requested };
      writeMark(mark);
      setPending(mark);
    }
  }, [running, info]);

  // Ответ поднявшегося бэкенда — единственное надёжное «всё кончилось».
  const settled = pending !== null && !unreachable && info !== null && !running;
  // Страница уже открыта в той версии, что назвал бэкенд, — значит код в
  // браузере свежий и перечитывать его незачем.
  const pageIsCurrent = loadedVersion.current !== null && info?.currentVersion === loadedVersion.current;
  // Единственный итог, который надо держать на экране до действия человека:
  // версия встала, а в браузере всё ещё код прошлой. Об остальном (сорвалось,
  // страницу уже перезагрузили) рассказывает сам ответ, метка больше не нужна.
  const needsReload = settled && info?.install.status === "DONE" && !pageIsCurrent;

  const forget = useCallback(() => {
    clearMark();
    setPending(null);
  }, []);

  useEffect(() => {
    if (settled && !needsReload) forget();
  }, [settled, needsReload, forget]);

  useEffect(() => {
    if (!enabled || !installing) return undefined;
    const timer = window.setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [enabled, installing, load]);

  return {
    info,
    setInfo,
    reload: load,
    installing,
    unreachable,
    /** Установка завершилась, а страница всё ещё на прошлой версии. */
    finished: needsReload,
    /** Убрать сообщение о результате: показано и больше не нужно. */
    forget,
    /**
     * Пометить установку запущенной, не дожидаясь ответа сервера: прогресс
     * обязан появиться в тот же миг, когда нажали кнопку.
     */
    markPending: useCallback((version: string | null) => {
      const mark = { version, at: Date.now() };
      writeMark(mark);
      setPending(mark);
    }, []),
    /** Версия, до которой идёт установка, даже когда бэкенд молчит. */
    targetVersion: info?.install.version ?? pending?.version ?? null,
    /** Момент запуска установки — от него считается прошедшее время. */
    startedAt: info?.install.requestedAt ?? (pending ? new Date(pending.at).toISOString() : null),
  };
}
