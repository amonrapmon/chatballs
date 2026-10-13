import { useEffect, useState } from "react";
import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { fetchVisitorState } from "./emailApi";
import type { VisitorState } from "./emailTypes";
import { summarizeVisitor } from "./visitorState";
import "./email-continuation.css";

export function VisitorStateChip({ conversationId, paused = false }: { conversationId: number; paused?: boolean }) {
  // undefined — ответа ещё не было: до него о посетителе не утверждается ничего.
  const [state, setState] = useState<VisitorState | null | undefined>(undefined);
  useEffect(() => {
    if (paused) return;
    let active = true, fetching = false;
    async function refresh() {
      if (fetching) return;
      fetching = true;
      try { const next = await fetchVisitorState(conversationId); if (active) setState(next); }
      catch { if (active) setState(null); }
      finally { fetching = false; }
    }
    void refresh(); const timer = setInterval(() => void refresh(), 4000);
    return () => { active = false; clearInterval(timer); };
  }, [conversationId, paused]);
  if (state === undefined) return null;
  const summary = summarizeVisitor(state), { kind } = summary;
  const minutes = summary.since ? Math.max(0, Math.floor((Date.now() - Date.parse(summary.since)) / 60000)) : 0;
  const timeKey = kind === "closed" ? "visitor.closed_time" : kind === "hidden" ? "visitor.hidden_time" : kind === "lost" ? "visitor.lost_time" : null;
  const icon = kind === "open" ? "eye" : kind === "closed" || kind === "hidden" ? "eyeOff" : kind === "lost" ? "refresh" : "info";
  return <span className={`visitor-state-chip is-${kind}`} title={t(`visitor.${kind}_hint`)}>
    <Icon name={icon} size={12} />{minutes && timeKey ? t(timeKey, { minutes: fmt.number(minutes) }) : t(`visitor.${kind}`)}
  </span>;
}
