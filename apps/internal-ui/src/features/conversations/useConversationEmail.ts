import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { fetchEmailOperations, fetchEmailOptions, retryEmail, sendEmail } from "./emailApi";
import type { EmailDraft, EmailOperation, EmailOptions } from "./emailTypes";

export function useConversationEmail(id: number, enabled: boolean, messageIds: string) {
  const [options, setOptions] = useState<EmailOptions | null>(null);
  const [operations, setOperations] = useState<EmailOperation[]>([]);
  const [busy, setBusy] = useState(false);
  const [sentId, setSentId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const inFlight = useRef(false);
  const actionInFlight = useRef(false);
  const active = useRef(true);
  const request = useRef<{ draft: EmailDraft; key: string } | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled || inFlight.current) return;
    inFlight.current = true;
    const [mail, journal] = await Promise.allSettled([
      fetchEmailOptions(id), fetchEmailOperations(id, messageIds ? messageIds.split(",").map(Number) : []),
    ]);
    if (active.current) {
      if (mail.status === "fulfilled") setOptions(mail.value);
      else {
        setOptions(null);
        if (!(mail.reason instanceof ApiError && [403, 404, 409].includes(mail.reason.status))) setLoadError(String(mail.reason.message));
      }
      if (journal.status === "fulfilled") {
        const requested = new Set(messageIds.split(",").map(Number));
        setOperations((previous) => [...journal.value.items, ...previous.filter((row) =>
          !requested.has(row.messageId) && !journal.value.items.some((next) => next.id === row.id))]);
      } else { setOperations([]); setLoadError(String(journal.reason.message)); }
      if (mail.status === "fulfilled" && journal.status === "fulfilled") setLoadError("");
    }
    inFlight.current = false;
  }, [id, enabled, messageIds]);

  useEffect(() => {
    active.current = true;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => { active.current = false; clearInterval(timer); };
  }, [refresh]);

  async function send(draft: EmailDraft) {
    if (actionInFlight.current || busy || !enabled) return false;
    actionInFlight.current = true;
    const old = request.current?.draft;
    if (!old || old.recipient !== draft.recipient || old.connectionId !== draft.connectionId || old.subject !== draft.subject || old.text !== draft.text || old.file !== draft.file) {
      request.current = { draft, key: crypto.randomUUID() };
    }
    setBusy(true); setError("");
    try {
      const operation = await sendEmail(id, draft, request.current!.key);
      if (!active.current) return false;
      setOperations((rows) => [operation, ...rows.filter((row) => row.id !== operation.id)]);
      setSentId(operation.id);
      request.current = null;
      return true;
    } catch (failure) {
      if (active.current) setError(failure instanceof Error ? failure.message : String(failure));
      return false;
    } finally { actionInFlight.current = false; if (active.current) setBusy(false); }
  }

  async function retry(operation: EmailOperation) {
    if (actionInFlight.current || busy || !operation.retryAllowed) return;
    actionInFlight.current = true;
    setBusy(true); setError("");
    try { await retryEmail(id, operation); await refresh(); }
    catch (failure) { if (active.current) setError(failure instanceof Error ? failure.message : String(failure)); }
    finally { actionInFlight.current = false; if (active.current) setBusy(false); }
  }
  const sent = operations.find((operation) => operation.id === sentId);
  const awaiting = Boolean(sent?.attempts.some((attempt) => attempt.state === "PENDING" || attempt.state === "SENDING"));
  return { options, operations, busy: busy || awaiting, error: error || loadError, send, retry, refresh };
}
