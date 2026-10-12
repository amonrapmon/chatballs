import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { t } from "../../i18n";
import { useRealtime, useRealtimeEvent } from "../realtime/RealtimeProvider";
import {
  fetchReplyAttempt, operationKey, rejectReplySuggestion, requestReplySuggestion,
  sendSuggestedReply, type ReplyAttempt,
} from "./replyAssistanceApi";
import { availableVariants, draftView, failedSuggestion, isPending } from "./replyDraft";

/** Предложение, текст которого вставлен в поле: связь уходит с ручной отправкой. */
export type LinkedSuggestion = { suggestionId: string; originalText: string };

const messageOf = (error: unknown) => (error instanceof Error ? error.message : t("common.request_failed"));

// Помощь в редакторе ответа. Генерация идёт на сервере в фоне: событие сокета
// сообщает, что состояние изменилось, а текст дочитывается защищённым запросом.
// Опрос — страховка на случай обрыва сокета и для просроченных операций.
export function useReplyAssistance(conversationId: number | null, onError: (message: string) => void) {
  const { connected } = useRealtime();
  const [attempt, setAttempt] = useState<ReplyAttempt | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dismissedId, setDismissedId] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [requestError, setRequestError] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [rejected, setRejected] = useState(false);
  const [linked, setLinked] = useState<LinkedSuggestion | null>(null);
  const attemptRef = useRef<ReplyAttempt | null>(null);
  // Ответ на чтение, начатое до более свежего изменения, применять нельзя:
  // он стёр бы только что запрошенный вариант.
  const revisionRef = useRef(0);
  const sendKeyRef = useRef<{ text: string; key: string } | null>(null);

  const show = useCallback((next: ReplyAttempt | null) => {
    const before = attemptRef.current;
    if (next && before?.id === next.id) {
      // Вариант, которого ждали, готов — показываем его.
      const awaited = new Set(before.suggestions.filter(isPending).map((suggestion) => suggestion.id));
      const arrived = availableVariants(next).filter((variant) => awaited.has(variant.id)).at(-1);
      if (arrived) setSelectedId(arrived.id);
    }
    revisionRef.current += 1;
    attemptRef.current = next;
    setAttempt(next);
  }, []);

  const read = useCallback(async () => {
    const current = attemptRef.current;
    if (conversationId == null || !current) return;
    const revision = revisionRef.current;
    try {
      const fresh = await fetchReplyAttempt(conversationId, current.id);
      if (revisionRef.current === revision) show(fresh);
    } catch (error) {
      // Право ответа отозвали или диалог удалён: ждать результата больше нечего.
      if (!(error instanceof ApiError) || (error.status !== 403 && error.status !== 404)) return;
      if (revisionRef.current !== revision) return;
      show(null);
      setRequestError(error.message);
    }
  }, [conversationId, show]);

  // Чтения идут по одному: событие, пришедшее во время запроса, не теряется,
  // а запускает ещё одно чтение следом.
  const readingRef = useRef({ active: false, again: false });
  const refresh = useCallback(async () => {
    const reading = readingRef.current;
    if (reading.active) {
      reading.again = true;
      return;
    }
    reading.active = true;
    try {
      do {
        reading.again = false;
        await read();
      } while (reading.again);
    } finally {
      reading.active = false;
    }
  }, [read]);

  // Другой диалог — другая попытка: панель и связь с прежним не переносятся.
  useEffect(() => {
    show(null);
    setSelectedId(null);
    setDismissedId(null);
    setRequestError("");
    setRejected(false);
    setLinked(null);
    sendKeyRef.current = null;
  }, [conversationId, show]);

  useRealtimeEvent("reply_assistance.changed", (message) => {
    if (message.conversationId === conversationId) void refresh();
  });

  const waiting = Boolean(attempt?.suggestions.some(isPending));
  useEffect(() => {
    if (!waiting) return;
    const timer = setInterval(() => void refresh(), connected ? 10000 : 3000);
    return () => clearInterval(timer);
  }, [waiting, connected, refresh]);

  async function request(alternative: boolean) {
    if (conversationId == null || requesting) return;
    const base = alternative ? attemptRef.current : null;
    setRequestError("");
    setRejected(false);
    if (!base) show(null);
    setRequesting(true);
    try {
      const suggestion = await requestReplySuggestion(conversationId, operationKey(), base?.id);
      const known = attemptRef.current?.id === suggestion.attemptId ? attemptRef.current.suggestions : [];
      show({ id: suggestion.attemptId, suggestions: [...known.filter((item) => item.id !== suggestion.id), suggestion] });
    } catch (error) {
      setRequestError(messageOf(error));
    } finally {
      setRequesting(false);
    }
  }

  const view = draftView({ attempt, selectedId, dismissedId, requesting, requestError });

  /** «×» на панели ошибки: закрывает сообщение, готовые варианты остаются. */
  function dismiss() {
    if (requestError) {
      setRequestError("");
      return;
    }
    const failed = failedSuggestion(attemptRef.current, dismissedId);
    if (failed) setDismissedId(failed.id);
  }

  /** «×» на панели черновика: решение оператора сохраняется на сервере. */
  async function reject() {
    const targets = availableVariants(attemptRef.current);
    if (conversationId == null || targets.length === 0 || rejecting) return;
    setRejecting(true);
    try {
      await Promise.all(targets.map((variant) => rejectReplySuggestion(conversationId, variant.id)));
      show(null);
      setRejected(true);
    } catch (error) {
      onError(messageOf(error));
    } finally {
      setRejecting(false);
    }
  }

  /** «Вставить в ответ»: отдаёт текст полю и закрывает панель. Ничего не отправляет. */
  function insert(): string | null {
    if (view?.kind !== "ready") return null;
    const variant = view.variants[view.selected];
    sendKeyRef.current = null;
    setLinked({ suggestionId: variant.id, originalText: variant.text });
    setRejected(false);
    show(null);
    return variant.text;
  }

  /** Ручная отправка текста из поля со ссылкой на исходное предложение. */
  async function send(text: string) {
    if (conversationId == null || !linked) return;
    // Повтор той же отправки идёт с прежним ключом: сервер вернёт уже
    // записанное сообщение, а не создаст второе.
    const previous = sendKeyRef.current;
    const key = previous?.text === text ? previous.key : operationKey();
    sendKeyRef.current = { text, key };
    await sendSuggestedReply(conversationId, text, linked.suggestionId, key);
    sendKeyRef.current = null;
    setLinked(null);
  }

  const unlink = useCallback(() => setLinked(null), []);

  return {
    view,
    busy: requesting || waiting,
    rejecting,
    rejected,
    linked,
    request: () => void request(false),
    rephrase: () => void request(true),
    retry: () => void request(availableVariants(attemptRef.current).length > 0),
    select: setSelectedId,
    dismiss,
    reject: () => void reject(),
    insert,
    send,
    unlink,
  };
}

export type ReplyAssistance = ReturnType<typeof useReplyAssistance>;
