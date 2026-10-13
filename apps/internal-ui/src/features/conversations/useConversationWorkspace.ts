import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { controlModeOf, fetchConversation, toConversationListItem, type ApiConversation, type ConversationCounters } from "./model";
import type { ListSort, ListTab } from "./types";
import { scopeFilters, type DialogScope } from "./workspaceScope";
import { useConversationCall } from "./useConversationCall";
import { useConversationEvents } from "./useConversationEvents";
import { useConversationActions } from "./useConversationActions";
import { useDebounced } from "../../shared/useDebounced";
import { useOpenedConversationRead } from "../notifications/useOpenedConversationRead";
import { useConversationFeed } from "./useConversationFeed";
import { useConversationList } from "./useConversationList";
import { useDialogKeyboardNav } from "./useDialogKeyboardNav";
import { useIncomingMessageSound } from "./useIncomingMessageSound";
import { t } from "../../i18n";
import { supervisionRevocation, withoutConversationActions, type SupervisionRevocation } from "./supervision";

export function useConversationWorkspace({ initialConversationId, scope, counters, viewerId }: {
  initialConversationId?: number | null; scope: DialogScope;
  counters: ConversationCounters | null; viewerId: number | null;
}) {
  const [listTab, setListTab] = useState<ListTab>("all");
  const [sort, setSort] = useState<ListSort>("activity");
  // Кадр S2: на ≤1024px контекст-панель — выдвижная поверх ленты.
  const [ctxOpen, setCtxOpen] = useState(false);
  // Кадры M1/M2: на ≤768px список и лента — отдельные экраны.
  const [mobileDialogOpen, setMobileDialogOpen] = useState(false);
  const [listCollapsed, setListCollapsed] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(initialConversationId ?? null);
  const [detail, setDetail] = useState<ApiConversation | null>(null);
  const lastDetail = useRef<ApiConversation | null>(null);
  const [detailError, setDetailError] = useState("");
  const [accessLost, setAccessLost] = useState("");
  const [revocation, setRevocation] = useState<SupervisionRevocation | null>(null);
  const revokedConversation = useRef<ApiConversation | null>(null);
  const selectedIndex = useRef(0);
  const [actionError, setActionError] = useState("");
  const selectedIdRef = useRef<number | null>(selectedId);
  selectedIdRef.current = selectedId;

  // Поиск, вкладка и порядок — параметры запроса: список приходит окном, и
  // фильтровать в браузере было бы нечего.
  // Ввод в поиске придерживается: запрос уходит, когда человек перестал печатать.
  const settledSearch = useDebounced(search.trim());
  const query = useMemo(() => ({
    ...scopeFilters(scope),
    ...(listTab === "queue" ? { queue: true } : {}),
    ...(listTab === "onMe" ? { waitingOnMe: true } : {}),
    ...(listTab === "mine" ? { assigned: "me" as const } : {}),
    ...(settledSearch ? { q: settledSearch } : {}),
    sort,
  }), [listTab, scope, settledSearch, sort]);
  // Оповещения ведут обновление, опрос остаётся страховкой: при обрыве сокета
  // всё возвращается к прежним интервалам само.
  const events = useConversationEvents({
    conversationId: selectedId,
    onInboxChanged: () => { void list.refresh(); if (selectedIdRef.current != null) void loadDetail(selectedIdRef.current); },
    onConversationChanged: (changedId) => {
      if (changedId !== selectedIdRef.current) return;
      void feed.catchUpMessages();
      void loadDetail(changedId);
    },
    onCommentsChanged: (changedId) => {
      if (changedId === selectedIdRef.current) void feed.catchUpComments();
    },
  });
  const list = useConversationList(query, { live: events.connected });
  const lastListRow = useRef<ApiConversation | null>(null);
  const currentListRow = list.conversations.find((item) => item.id === selectedId);
  if (currentListRow && !revocation) lastListRow.current = currentListRow;
  const feed = useConversationFeed(selectedId, { live: events.connected, paused: Boolean(revocation) });

  const loadDetail = useCallback(async (id: number) => {
    try {
      const loaded = await fetchConversation(id);
      if (selectedIdRef.current === id) {
        lastDetail.current = loaded;
        setDetail(loaded);
        setDetailError("");
        setRevocation(null);
        revokedConversation.current = null;
      }
    } catch (error) {
      if (selectedIdRef.current !== id) return;
      // Диалог удалили — возможно, другим администратором. Карточки больше
      // нет, и держать выбор не на чем; список обновит событие инбокса.
      if (error instanceof ApiError && error.status === 404) {
        const previous = lastDetail.current;
        const loss = previous?.id === id ? supervisionRevocation(error.payload, previous) : null;
        if (loss && previous) {
          revokedConversation.current = withoutConversationActions({ ...previous,
            lastMessage: lastListRow.current?.id === id ? lastListRow.current.lastMessage : previous.lastMessage,
          });
          setDetail(revokedConversation.current);
          setRevocation(loss);
          setActionError("");
          setDetailError("");
          return;
        }
        list.discard(id);
        void list.refresh();
        const actor = error.payload.participationEndedBy;
        setAccessLost(typeof actor === "string" && previous?.id === id && previous.contact?.name && previous.access?.isParticipant
          ? t("participants.lost_message", { actor, contact: previous.contact.name }) : error.message);
        setSelectedId(null);
        setDetail(null);
        setDetailError("");
        return;
      }
      setDetailError(t("conversations.could_not_load_conversation"));
    }
  }, [list.discard, list.refresh]);

  useEffect(() => {
    if (initialConversationId != null) setSelectedId(initialConversationId);
  }, [initialConversationId]);

  useEffect(() => {
    if (!accessLost) setSelectedId((current) => current ?? list.conversations[0]?.id ?? null);
  }, [list.conversations, accessLost]);

  useEffect(() => {
    setCtxOpen(false);
    setRevocation(null);
    revokedConversation.current = null;
  }, [selectedId]);

  useOpenedConversationRead(selectedId);

  useEffect(() => {
    if (selectedId == null) return;
    setDetail(null);
    setDetailError("");
    setActionError("");
    void loadDetail(selectedId);
    // Карточка диалога (статус, ответственный, метки) обновляется отдельно от
    // ленты: сообщений она больше не несёт. С живыми оповещениями опрос — тоже
    // страховка.
    const timer = setInterval(() => loadDetail(selectedId), events.connected ? 30000 : 3000);
    return () => clearInterval(timer);
  }, [events.connected, selectedId, loadDetail]);

  const onConversationChanged = useCallback(() => {
    if (selectedId != null) void loadDetail(selectedId);
  }, [loadDetail, selectedId]);
  const callController = useConversationCall({ conversationId: selectedId, onConversationChanged });
  useIncomingMessageSound(list.conversations, list.loaded);

  const dialogs = useMemo(
    () => {
      const items = [...list.conversations];
      if (revokedConversation.current && revocation) {
        const index = items.findIndex((item) => item.id === revokedConversation.current?.id);
        if (index >= 0) items.splice(index, 1);
        items.splice(Math.min(selectedIndex.current, items.length), 0, revokedConversation.current);
      } else {
        const index = items.findIndex((item) => item.id === selectedId);
        if (index >= 0) selectedIndex.current = index;
      }
      return items.map((item) => toConversationListItem(item, { viewerId, assignmentTimeoutMinutes: counters?.assignmentTimeoutMinutes }));
    },
    [list.conversations, viewerId, counters?.assignmentTimeoutMinutes, revocation, selectedId],
  );
  useDialogKeyboardNav({
    dialogs,
    selectedId,
    setSelectedId,
    onOpen: () => setMobileDialogOpen(true),
  });

  // A list refresh can remove the row before the detail reports revocation.
  // Keep the opened view mounted so its loaded context and history survive K8.
  const cachedRow = lastListRow.current?.id === selectedId ? lastListRow.current : null;
  const selectedDialog = dialogs.find((dialog) => dialog.id === selectedId)
    ?? (cachedRow && detail?.id === selectedId ? toConversationListItem(cachedRow, { viewerId, assignmentTimeoutMinutes: counters?.assignmentTimeoutMinutes }) : null);
  const detailLoaded = detail?.id === selectedId;
  const controlMode = detailLoaded ? controlModeOf(detail) : "waiting";

  function applyUpdated(updated: ApiConversation) {
    if (revokedConversation.current || updated.id !== selectedIdRef.current) return;
    lastDetail.current = updated;
    setDetail(updated);
    setActionError("");
    void list.refresh();
  }

  const actions = useConversationActions({
    selectedId, applyUpdated, setError: setActionError,
    clearSelected: () => { setDetail(null); setSelectedId(null); void list.refresh(); },
  });
  return {
    listTab, setListTab, sort, setSort, ctxOpen, setCtxOpen, mobileDialogOpen,
    setMobileDialogOpen, listCollapsed, setListCollapsed, search, setSearch,
    selectedId, setSelectedId, detail, detailError, actionError, setActionError,
    settledSearch, list, feed, callController, dialogs, selectedDialog,
    detailLoaded, controlMode, applyUpdated, accessLost, setAccessLost, revocation,
    clearRevocation: () => { if (selectedId != null) list.discard(selectedId); revokedConversation.current = null; setRevocation(null); setDetail(null); setSelectedId(null); }, ...actions,
  };
}
