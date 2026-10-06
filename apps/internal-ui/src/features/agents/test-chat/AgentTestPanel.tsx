import { useEffect, useId, useRef, useState } from "react";
import { t } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { ErrorScreen, LoadingState } from "../../../shared/ui";
import type { AgentCard } from "../model";
import { validClientData } from "./model";
import { TestChatFeed } from "./TestChatFeed";
import { TestClientData } from "./TestClientData";
import { useAgentTestChat } from "./useAgentTestChat";
import "./styles.css";

export function AgentTestPanel({ card, onClose }: { card: AgentCard; onClose: () => void }) {
  const chat = useAgentTestChat(card.id);
  const [message, setMessage] = useState("");
  const titleId = useId();
  const input = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    return () => opener?.focus();
  }, []);
  const disabled = chat.busy || !chat.connections || !validClientData(chat.values, chat.connections);
  return <aside className="agent-test-panel" ref={panel} tabIndex={-1} role="dialog" aria-labelledby={titleId}
    onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } }}>
    <header className="agent-test-head">
      <div><strong id={titleId}>{t("agent_test.title")}</strong><small>{t("agent_test.subtitle")}</small></div>
      <button type="button" title={t("agent_test.restart")} aria-label={t("agent_test.restart")}
        onClick={() => { chat.restart(); setMessage(""); input.current?.focus(); }}><Icon name="refresh" size={15} strokeWidth={2.2} /></button>
      <button type="button" title={t("common.close")} aria-label={t("common.close")} onClick={onClose}><Icon name="close" size={15} strokeWidth={2.4} /></button>
    </header>
    {chat.loadError ? <ErrorScreen retry={chat.reload} /> : !chat.connections ? <LoadingState /> :
      <TestClientData connections={chat.connections} values={chat.values} onChange={chat.setValues} disabled={chat.busy} />}
    <TestChatFeed turns={chat.turns} agentName={card.name} />
    <form className="agent-test-composer" onSubmit={(event) => {
      event.preventDefault();
      if (!disabled && message.trim()) { void chat.send(message); setMessage(""); }
    }}>
      <div><input ref={input} value={message} aria-label={t("agent_test.placeholder")} placeholder={t("agent_test.placeholder")}
        onChange={(event) => setMessage(event.target.value)} disabled={chat.busy} maxLength={10000} />
        <button type="submit" disabled={disabled || !message.trim()} aria-busy={chat.busy}>{t("conversations.send")}</button>
      </div>
    </form>
  </aside>;
}
