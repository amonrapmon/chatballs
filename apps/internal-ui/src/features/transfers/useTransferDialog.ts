import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { t } from "../../i18n";
import { allPages } from "../../shared/allPages";
import { useDebounced } from "../../shared/useDebounced";
import { fetchChatDirectory, fetchConversation, type ApiConversation, type ChatDirectoryEmployee } from "../conversations/model";
import { useRealtimeEvent } from "../realtime/RealtimeProvider";
import { errorText, fetchTransferOptions, transferConversation, type TransferReasonOption } from "./api";

export function useTransferDialog(detail: ApiConversation, onUpdated: (next: ApiConversation) => void, onTransferred: (name: string) => void) {
  const [query, setQuery] = useState("");
  const settled = useDebounced(query);
  const [people, setPeople] = useState<ChatDirectoryEmployee[]>([]);
  const [reasons, setReasons] = useState<TransferReasonOption[]>([]);
  const [recipient, setRecipient] = useState<number | null>(null);
  const [reason, setReason] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reasonError, setReasonError] = useState("");
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const [unavailableName, setUnavailableName] = useState("");
  const alive = useRef(true);
  const generation = useRef(0);
  const directoryRequest = useRef<{ key: string; promise: Promise<void> } | null>(null);
  const initialVersion = useRef(detail.assignmentVersion);
  const selection = useRef(recipient); selection.current = recipient;
  const pending = useRef(false);
  const operation = useRef({ fingerprint: "", id: "" });
  const reloadPeople = useCallback(async () => {
    const key = JSON.stringify([settled, detail.assignedOperatorId]);
    if (directoryRequest.current?.key === key) return directoryRequest.current.promise;
    const current = ++generation.current;
    const request = (async () => {
      try {
        const directory = await fetchChatDirectory(settled);
        if (!alive.current || current !== generation.current) return;
        const rows = directory.employees.filter((person) => person.id !== detail.assignedOperatorId);
        setPeople(rows);
        const selected = directory.employees.find((person) => person.id === selection.current);
        if (selected && !selected.assignmentAllowed) {
          setUnavailableName(selected.name); setRecipient(null); setError("");
        }
        setLoading(false);
      } catch (problem) {
        if (alive.current && current === generation.current) {
          setError(errorText(problem)); setLoading(false);
        }
      }
    })();
    directoryRequest.current = { key, promise: request };
    try { await request; }
    finally {
      if (directoryRequest.current?.promise === request) directoryRequest.current = null;
    }
  }, [detail.assignedOperatorId, settled]);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);
  useEffect(() => {
    void reloadPeople();
    const timer = setInterval(() => void reloadPeople(), 30000);
    return () => { clearInterval(timer); };
  }, [reloadPeople]);
  useRealtimeEvent("work_status.changed", () => void reloadPeople());
  useEffect(() => {
    allPages((page) => fetchTransferOptions(detail.id, page))
      .then((items) => { if (alive.current) setReasons(items); })
      .catch((problem) => { if (alive.current) setError(errorText(problem)); });
  }, [detail.id]);

  async function submit() {
    if (pending.current || conflict) return;
    if (!reason) { setReasonError(t("transfers.reason_required")); return; }
    if (!recipient) return;
    const fingerprint = JSON.stringify([recipient, reason, comment, initialVersion.current]);
    if (operation.current.fingerprint !== fingerprint) {
      operation.current = { fingerprint, id: crypto.randomUUID() };
    }
    pending.current = true; setBusy(true); setError(""); setReasonError("");
    try {
      await transferConversation(detail.id, {
        userId: recipient, reasonId: reason, comment,
        expectedVersion: initialVersion.current, operationId: operation.current.id,
      });
      if (!alive.current) return;
      // A refresh failure cannot turn a committed transfer into a failed one.
      try {
        const fresh = await fetchConversation(detail.id);
        if (alive.current) onUpdated(fresh);
      } catch { /* The workspace also refreshes after the completed operation. */ }
      if (alive.current) onTransferred(people.find((person) => person.id === recipient)?.name ?? "");
    } catch (problem) {
      if (!alive.current) return;
      setError(errorText(problem));
      if (problem instanceof ApiError && problem.status === 409) {
        setConflict(true);
        try {
          const fresh = await fetchConversation(detail.id);
          if (alive.current) onUpdated(fresh);
        } catch (refreshError) { if (alive.current) setError(errorText(refreshError)); }
      } else if (problem instanceof ApiError && problem.status === 400) {
        await reloadPeople();
        try {
          const freshReasons = await allPages((page) => fetchTransferOptions(detail.id, page));
          if (alive.current) {
            setReasons(freshReasons);
            if (!freshReasons.some((item) => item.id === reason)) setReason(null);
          }
        } catch (refreshError) { if (alive.current) setError(errorText(refreshError)); }
      }
    } finally {
      pending.current = false;
      if (alive.current) setBusy(false);
    }
  }
  return {
    query, setQuery, people, reasons, recipient, reason, comment, setComment,
    busy, loading, reasonError, error, conflict, unavailableName, submit,
    choose: (id: number) => { setRecipient(id); setUnavailableName(""); setError(""); },
    selectReason: (id: number) => { setReason(id); setReasonError(""); },
  };
}
