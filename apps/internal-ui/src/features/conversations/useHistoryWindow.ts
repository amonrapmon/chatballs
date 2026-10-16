import { useCallback, useEffect, useRef, useState } from "react";

import type { WindowPage } from "./apiTypes";
import type { MessageWindowQuery } from "./conversationApi";
import { reconcileHistoryDelta } from "./historyDelta";
import { t } from "../../i18n";

// Открытие диалога показывает хвост ленты; вверх она догружается по прокрутке,
// вниз — дельтой обновления. Целиком лента не запрашивается никогда: записей в
// диалоге может быть сколько угодно. Так устроены обе ленты диалога — сообщения
// и внутренние комментарии: у каждой свой endpoint и свой курсор.
const HISTORY_WINDOW = 50;
// Пока оповещения живы, опрос — только страховка на случай потерянного события.
const DELTA_INTERVAL_MS = 3000;
const DELTA_IDLE_INTERVAL_MS = 30000;

export type HistoryWindow<T> = {
  items: T[];
  loaded: boolean;
  hasOlder: boolean;
  loadingOlder: boolean;
  errorText: string;
  loadOlder: () => void;
  /** Подтянуть то, что появилось после последней показанной записи. */
  catchUp: () => Promise<void>;
};

type FetchWindow<T> = (conversationId: number, query: MessageWindowQuery) => Promise<WindowPage<T> & { removedIds?: number[] }>;

function rememberRemovedIds(ids: Set<number>, page: { removedIds?: number[] }): void {
  for (const id of page.removedIds ?? []) ids.add(id);
}

/** fetchWindow — функция уровня модуля: от её идентичности зависит перезагрузка. */
export function useHistoryWindow<T extends { id: number }>(
  conversationId: number | null,
  fetchWindow: FetchWindow<T>,
  { live = false, paused = false }: { live?: boolean; paused?: boolean } = {},
): HistoryWindow<T> {
  const [items, setItems] = useState<T[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [hasOlder, setHasOlder] = useState(false);
  const [olderCursor, setOlderCursor] = useState<number | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [errorText, setErrorText] = useState("");
  // Курсор дельты — последний показанный id; ref, чтобы поллинг не пересоздавался
  // на каждую новую запись. Ноль — лента загружена, но пока пуста.
  const lastIdRef = useRef(0);
  // Не дать поздней загрузке старого окна вернуть уже отозванное сообщение.
  const removedIdsRef = useRef(new Set<number>());
  const loadedRef = useRef(false);
  const conversationRef = useRef<number | null>(conversationId);
  conversationRef.current = conversationId;
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    setItems([]);
    setLoaded(false);
    setHasOlder(false);
    setOlderCursor(null);
    lastIdRef.current = 0;
    removedIdsRef.current.clear();
    loadedRef.current = false;
    if (conversationId == null) return;
    let active = true;
    setErrorText("");
    fetchWindow(conversationId, { limit: HISTORY_WINDOW })
      .then((page) => {
        if (!active || conversationRef.current !== conversationId) return;
        rememberRemovedIds(removedIdsRef.current, page);
        setItems(reconcileHistoryDelta([], page, removedIdsRef.current));
        setHasOlder(page.hasMore);
        setOlderCursor(page.cursor);
        setLoaded(true);
        loadedRef.current = true;
        lastIdRef.current = page.items.length ? page.items[page.items.length - 1].id : 0;
      })
      .catch(() => {
        if (active && conversationRef.current === conversationId) setErrorText(t("conversations.could_not_load_conversation_history"));
      });
    return () => {
      active = false;
    };
  }, [conversationId, fetchWindow]);

  const catchUp = useCallback(async () => {
    const id = conversationRef.current;
    if (pausedRef.current || id == null || !loadedRef.current) return;
    const lastId = lastIdRef.current;
    try {
      // У пустой ленты курсора ещё нет: первая запись приходит обычным окном.
      const page = await fetchWindow(id, lastId ? { after: lastId } : { limit: HISTORY_WINDOW });
      if (pausedRef.current || conversationRef.current !== id) return;
      rememberRemovedIds(removedIdsRef.current, page);
      if (page.items.length) {
        lastIdRef.current = Math.max(lastIdRef.current, page.items[page.items.length - 1].id);
      }
      setItems((current) => reconcileHistoryDelta(current, page, removedIdsRef.current));
      if (lastId === 0 && page.items.length) {
        setHasOlder(page.hasMore);
        setOlderCursor(page.cursor);
      }
      setErrorText("");
    } catch {
      setErrorText(t("conversations.could_not_refresh_conversation_history"));
    }
  }, [fetchWindow]);

  useEffect(() => {
    if (paused || conversationId == null || !loaded) return;
    const timer = setInterval(
      () => void catchUp(),
      live ? DELTA_IDLE_INTERVAL_MS : DELTA_INTERVAL_MS,
    );
    return () => clearInterval(timer);
  }, [catchUp, conversationId, live, loaded, paused]);

  const loadOlder = useCallback(() => {
    const id = conversationRef.current;
    if (pausedRef.current || id == null || olderCursor == null || loadingOlder) return;
    setLoadingOlder(true);
    fetchWindow(id, { before: olderCursor, limit: HISTORY_WINDOW })
      .then((page) => {
        if (pausedRef.current || conversationRef.current !== id) return;
        rememberRemovedIds(removedIdsRef.current, page);
        setItems((current) => reconcileHistoryDelta([...page.items, ...current], { ...page, items: [] }, removedIdsRef.current));
        setHasOlder(page.hasMore);
        setOlderCursor(page.cursor);
        setErrorText("");
      })
      .catch(() => {
        if (conversationRef.current === id) setErrorText(t("conversations.could_not_load_earlier_messages"));
      })
      .finally(() => {
        if (conversationRef.current === id) setLoadingOlder(false);
      });
  }, [fetchWindow, loadingOlder, olderCursor]);

  return { items, loaded, hasOlder, loadingOlder, errorText, loadOlder, catchUp };
}
