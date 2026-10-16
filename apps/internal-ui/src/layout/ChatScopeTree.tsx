import type { ReactNode } from "react";
import type { OrganizationMembership, RouteKey } from "../types";
import { Icon } from "../shared/icons";
import type { DialogScope } from "../features/conversations/ConversationWorkspace";
import { agentColorOf, groupColorOf, type ConversationCounters } from "../features/conversations/model";
import { t } from "../i18n";
import "./chat-scope-icons.css";

// Дерево «Диалоги» сотрудника (кадры A-H): пункты — это охват списка чата.
export function ChatScopeTree({
  route,
  scope,
  counters,
  setScope,
  supervision,
  footer,
}: {
  route: RouteKey;
  scope: DialogScope;
  counters: ConversationCounters | null;
  setScope: (scope: DialogScope) => void;
  supervision?: OrganizationMembership;
  footer?: ReactNode;
}) {
  const inChat = route === "chat";
  const isActive = (candidate: DialogScope) =>
    inChat
    && scope.kind === candidate.kind
    && (scope.kind !== "group" || candidate.kind !== "group" || scope.id === candidate.id)
    && (scope.kind !== "agent" || candidate.kind !== "agent" || scope.id === candidate.id);

  return (
    <nav className="hub-nav chat-scope-tree">
      <div className="chat-scope-head"><Icon name="message" size={17} strokeWidth={1.9} /><span>{t("common.conversations")}</span><span className="chat-scope-chevron"><Icon name="chevron" size={14} strokeWidth={2} /></span></div>
      <button
        className={`chat-scope-item is-top ${isActive({ kind: "all" }) ? "is-active" : ""}`}
        type="button"
        onClick={() => setScope({ kind: "all" })}
      >
        <Icon name="inbox" size={15} strokeWidth={1.9} />
        <span>{t("profile.all_conversations")}</span>
        {counters && <small>{counters.all}</small>}
      </button>
      {counters && (
        <>
          <div className="chat-scope-section"><Icon name="team" size={15} strokeWidth={1.9} /><span>{t("common.groups")}</span><span className="chat-scope-chevron"><Icon name="chevron" size={13} strokeWidth={2} /></span></div>
          {counters.groups.map((group) => (
            <button
              className={`chat-scope-item is-nested ${isActive({ kind: "group", id: group.id, label: group.name }) ? "is-active" : ""}`}
              key={group.id}
              type="button"
              onClick={() => setScope({ kind: "group", id: group.id, label: group.name })}
            >
              <i className="chat-scope-dot" style={{ background: groupColorOf(group.id, group.color) }} />
              <span>{group.name}</span>
              {supervision?.supervisionCapabilities?.includes("conversations.view") && supervision.supervisedGroups?.some((item) => item.id === group.id) && <Icon name="shield" size={13} />}
              <small>{group.count}</small>
            </button>
          ))}
          {counters.groups.length > 0 && (
            <button
              className={`chat-scope-item is-nested ${isActive({ kind: "ungrouped" }) ? "is-active" : ""}`}
              type="button"
              onClick={() => setScope({ kind: "ungrouped" })}
            >
              <i className="chat-scope-dot is-muted" />
              <span>{t("common.no_group")}</span>
              <small>{counters.ungrouped}</small>
            </button>
          )}
        </>
      )}
      {counters && (
        <>
          <div className="chat-scope-section"><Icon name="robot" size={15} strokeWidth={1.9} /><span>{t("common.agents")}</span><span className="chat-scope-chevron"><Icon name="chevron" size={13} strokeWidth={2} /></span></div>
          {counters.agents.map((agent) => (
            <button
              className={`chat-scope-item is-nested ${isActive({ kind: "agent", id: agent.id, label: agent.name }) ? "is-active" : ""}`}
              key={agent.id}
              type="button"
              onClick={() => setScope({ kind: "agent", id: agent.id, label: agent.name })}
            >
              <span className="chat-scope-agent" style={{ color: agentColorOf(agent.id), background: `color-mix(in srgb, ${agentColorOf(agent.id)} 16%, var(--surface-card))` }}><Icon name="robot" size={11} strokeWidth={2.2} /></span>
              <span>{agent.name}</span>
              <small>{agent.count}</small>
            </button>
          ))}
        </>
      )}
      {supervision?.role === "SUPERVISOR" && !supervision.supervisedGroups?.length && <p className="chat-supervision-note">{t("supervision.empty_tree")}</p>}
      {footer}
    </nav>
  );
}
