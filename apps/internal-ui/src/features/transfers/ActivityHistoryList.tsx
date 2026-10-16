import { useEffect, useRef } from "react";
import { LoadingState } from "../../shared/ui";
import type { ActivityFilter } from "./activityApi";
import { ActivityHistoryRow } from "./ActivityHistoryRow";
import { useActivityHistory } from "./useActivityHistory";

export function ActivityHistoryList({ conversationId, kind }: { conversationId: number; kind: ActivityFilter }) {
  const state = useActivityHistory(conversationId, kind);
  const scroll = useRef<HTMLDivElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!sentinel.current || !state.hasMore || state.busy || state.error) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) state.loadMore();
    }, { root: scroll.current });
    observer.observe(sentinel.current);
    return () => observer.disconnect();
  }, [state.busy, state.hasMore, state.error, state.loadMore]);
  return <div className="activity-history-list" ref={scroll}>
    {state.items.map((item) => <ActivityHistoryRow key={item.id} item={item} />)}
    {state.busy && <LoadingState />}
    {state.error && <p className="transfer-error" role="alert">{state.error}</p>}
    <div ref={sentinel} aria-hidden="true" />
  </div>;
}
