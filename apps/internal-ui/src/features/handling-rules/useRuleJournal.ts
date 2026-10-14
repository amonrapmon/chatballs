import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { PagedPayload } from "../../shared/usePagedResource";
import type { ApiConversation } from "../conversations/apiTypes";
import { useRealtimeEvent } from "../realtime/RealtimeProvider";
import { ruleErrors } from "./model";
import type { RuleExecution } from "./types";

export function useRuleJournal() {
  const [refresh, setRefresh] = useState({ revision: 0, clear: true });
  const loaded = useRef(false);
  const inFlight = useRef(false);
  const [entries, setEntries] = useState<RuleExecution[]>([]);
  const [names, setNames] = useState<Record<number, string>>({});
  const [timezone, setTimezone] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const invalidate = () => setRefresh(value => ({ revision: value.revision + 1, clear: true }));
  useRealtimeEvent("inbox.changed", invalidate);
  useRealtimeEvent("notifications.changed", invalidate);
  useEffect(() => {
    const focus = () => setRefresh(value => ({ revision: value.revision + 1, clear: true }));
    window.addEventListener("focus", focus);
    return () => window.removeEventListener("focus", focus);
  }, []);
  useEffect(() => {
    if (!entries.some(entry => entry.status === "PENDING")) return;
    const timer = window.setInterval(() => {
      if (!inFlight.current && document.visibilityState === "visible") setRefresh(value => ({ revision: value.revision + 1, clear: false }));
    }, 15_000);
    return () => window.clearInterval(timer);
  }, [entries]);
  useEffect(() => {
    const controller = new AbortController();
    inFlight.current = true;
    setLoading(!loaded.current || refresh.clear); setError("");
    if (refresh.clear) { setEntries([]); setNames({}); }
    async function load() {
      let zone = "";
      const items: RuleExecution[] = [];
      for (let page = 1; ; page++) {
        const response = await api<PagedPayload<RuleExecution> & { timezone: string }>(`/api/v1/conversations/rule-executions/?page=${page}&pageSize=100`, { signal: controller.signal });
        zone = response.timezone;
        items.push(...response.items);
        if (page >= response.pageCount) break;
      }
      const labels: Record<number, string> = {};
      const ids = [...new Set(items.map(item => item.conversationId))];
      // Every detail passes the normal server visibility check. A denied detail
      // keeps only the ID already returned by the scoped journal.
      for (let start = 0; start < ids.length; start += 5) {
        await Promise.all(ids.slice(start, start + 5).map(async id => {
          const response = await api<{ conversation: ApiConversation }>(`/api/v1/conversations/${id}/`, { signal: controller.signal }).catch(() => null);
          if (response) labels[id] = response.conversation.contact?.name ?? "";
        }));
        if (controller.signal.aborted) return;
      }
      if (controller.signal.aborted) return;
      setEntries([...new Map(items.map(item => [item.id, item])).values()]);
      loaded.current = true;
      setNames(labels); setTimezone(zone); setLoading(false);
    }
    load().catch(problem => { if (!controller.signal.aborted) { setEntries([]); setNames({}); setError(ruleErrors(problem).detail ?? ""); setLoading(false); } })
      .finally(() => { if (!controller.signal.aborted) inFlight.current = false; });
    return () => { controller.abort(); inFlight.current = false; };
  }, [refresh]);
  return { entries, names, timezone, error, loading };
}
