import { useEffect, useRef } from "react";
import { t } from "../../../i18n";
import { ToolCallChip } from "../../../shared/tool-calls/ToolCallChip";
import type { TestTurn } from "./model";

export function TestChatFeed({ turns, agentName }: { turns: TestTurn[]; agentName: string }) {
  const feed = useRef<HTMLDivElement>(null);
  useEffect(() => { if (feed.current) feed.current.scrollTop = feed.current.scrollHeight; }, [turns]);
  return <div className="agent-test-feed" role="log" aria-live="polite" ref={feed}>
    {turns.map((turn, index) => <div key={index}>
      <div className="agent-test-client"><div>{turn.message}</div></div>
      <ToolCallChip calls={turn.calls} createdAt={turn.createdAt} />
      {turn.reply !== undefined && <div className="agent-test-reply">
        <strong>{t("agent_test.agent_name", { name: agentName })}</strong><div>{turn.reply}</div>
      </div>}
      {turn.error && <div className="agent-test-error" role="alert">{turn.error}</div>}
    </div>)}
  </div>;
}
