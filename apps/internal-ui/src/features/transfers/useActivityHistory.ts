import { useCallback, useEffect, useRef, useState } from "react";
import { useRealtimeEvent } from "../realtime/RealtimeProvider";
import { errorText } from "./api";
import { fetchActivity, type ActivityFilter, type ActivityRecord } from "./activityApi";

export function useActivityHistory(conversationId: number, kind: ActivityFilter) {
  const [items, setItems] = useState<ActivityRecord[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const epoch = useRef(0);
  const pending = useRef(false);
  const refreshRequested = useRef(false);
  const loadRef = useRef<(page: number, reset: boolean) => Promise<void>>(async () => {});

  const load = useCallback(async (nextPage: number, reset: boolean) => {
    if (pending.current) {
      if (reset) refreshRequested.current = true;
      return;
    }
    const generation = epoch.current;
    pending.current = true; setBusy(true); setError("");
    try {
      const result = await fetchActivity(conversationId, kind, nextPage);
      if (generation !== epoch.current) return;
      setItems((previous) => {
        if (reset) return result.items;
        const known = new Set(previous.map((item) => item.id));
        return [...previous, ...result.items.filter((item) => !known.has(item.id))];
      });
      setPage(result.page); setHasMore(result.page < result.pageCount);
    } catch (problem) {
      if (generation === epoch.current) { setItems([]); setError(errorText(problem)); }
    } finally {
      if (generation === epoch.current) {
        pending.current = false; setBusy(false);
        if (refreshRequested.current) {
          refreshRequested.current = false;
          void loadRef.current(1, true);
        }
      }
    }
  }, [conversationId, kind]);
  loadRef.current = load;

  useEffect(() => {
    epoch.current++; pending.current = false; refreshRequested.current = false;
    setItems([]); setPage(0); setHasMore(true);
    void load(1, true);
    return () => { epoch.current++; };
  }, [load]);
  useRealtimeEvent("conversation.changed", (event) => {
    if (event.conversationId === conversationId) void loadRef.current(1, true);
  });

  return { items, busy, error, hasMore, loadMore: () => { if (hasMore && !error) void load(page + 1, false); } };
}
