import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { useAvailabilityRefresh } from "../work-status/useAvailabilityRefresh";
import { t } from "../../i18n";
import type { ApiConversation } from "./apiTypes";
import { addParticipant, fetchParticipants, removeParticipant, type ApiParticipant, type ParticipantRoster } from "./participantApi";

export function useParticipants(detail: ApiConversation) {
  const [roster, setRoster] = useState<ParticipantRoster | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ kind: "add" | "remove"; name: string; id?: number } | null>(null);
  const currentId = useRef(detail.id);
  currentId.current = detail.id;
  const refresh = useCallback(async () => {
    const id = detail.id;
    try {
      const loaded = await fetchParticipants(id);
      if (currentId.current === id) setRoster(loaded);
    } catch (problem) {
      if (currentId.current === id) setError(problem instanceof ApiError ? problem.message : t("participants.network_error"));
    }
  }, [detail.id]);
  useAvailabilityRefresh(() => void refresh());
  useEffect(() => { void refresh(); }, [refresh, detail]);
  useEffect(() => {
    setRoster(null); setError(""); setFailure(null);
    const timer = setInterval(() => void refresh(), 10000);
    return () => clearInterval(timer);
  }, [refresh]);

  async function mutate(kind: "add" | "remove", name: string, targetId: number, reason: string) {
    if (busy) return false;
    const id = detail.id;
    setBusy(true); setError(""); setFailure(null);
    try {
      if (kind === "add") await addParticipant(id, targetId, reason);
      else await removeParticipant(id, targetId, reason);
      if (currentId.current !== id) return false;
      await refresh();
      return true;
    } catch (problem) {
      if (currentId.current === id) {
        setFailure({ kind, name, id: targetId });
        setError(problem instanceof ApiError ? problem.message : t("participants.network_error"));
        // A limit/access change may have happened while the form was open.
        void refresh();
      }
      return false;
    } finally {
      if (currentId.current === id) setBusy(false);
    }
  }
  const items = (roster?.items ?? []).filter((row) => row.userId !== detail.assignedOperatorId);
  return { roster, items, busy, error, failure, refresh,
    add: (membershipId: number, name: string, reason: string) => mutate("add", name, membershipId, reason),
    remove: (row: ApiParticipant, reason: string) => mutate("remove", row.member.name, row.id, reason),
  };
}
