import { Dropdown } from "antd";
import { useState } from "react";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { ChannelGlyph } from "../../shared/badges";
import { groupColorOf } from "../conversations/model";
import { agentModelLabel, agentStatusMeta, agentTile, agentTint, type AgentCard } from "./model";

/** Строка списка (кадр G1). Вся строка открывает карточку. */
export function AgentRow({
  card,
  openAgent,
  onToggleAi,
}: {
  card: AgentCard;
  openAgent: (agentId: number) => void;
  onToggleAi: (card: AgentCard) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const tile = agentTile(card);
  const status = agentStatusMeta(card);
  const open = card.counters.openConversations;
  const menuItems = [
    {
      key: "open",
      label: (
        <button
          type="button"
          onClick={() => {
            setMenuOpen(false);
            openAgent(card.id);
          }}>
          <Icon name="external" size={15} />
          {t("admin.open_card")}
        </button>
      ),
    },
    { type: "divider" as const },
    {
      key: "toggle",
      label: (
        <button
          type="button"
          className={card.aiStatus === "ACTIVE" ? "warning" : ""}
          onClick={() => {
            setMenuOpen(false);
            onToggleAi(card);
          }}>
          <Icon name={card.aiStatus === "ACTIVE" ? "pause" : "bolt"} size={15} />
          {card.aiStatus === "ACTIVE" ? t("ai.stop_ai") : t("ai.start_ai")}
        </button>
      ),
    },
  ];

  return (
    <div
      className={`agents-row ${card.isActive ? "" : "is-off"}`}
      role="button"
      tabIndex={0}
      onClick={() => openAgent(card.id)}
      onKeyDown={(event) => {
        if (event.key === "Enter") openAgent(card.id);
      }}>
      <div className="agents-row-agent">
        <span className="agents-tile" style={{ background: tile.background, color: tile.color }}>
          <Icon name="robot" size={20} strokeWidth={1.9} />
        </span>
        <span>
          <strong>{card.name}</strong>
          <small>{card.code}</small>
        </span>
      </div>
      <span className={`agents-row-group ${card.groupId === null ? "is-none" : ""}`}>
        {card.groupId !== null && <i style={{ background: groupColorOf(card.groupId, card.groupColor) }} />}
        {card.groupName ?? t("common.no_group")}
      </span>
      <b className="agents-status" style={{ background: status.bg, color: status.color }}>
        <i />
        {status.text}
      </b>
      <span className="agents-row-model">{agentModelLabel(card)}</span>
      <div className="agents-row-conns">
        {card.connections.length === 0 ? (
          <span className="agents-row-dash">—</span>
        ) : (
          card.connections.map((connection) => {
            const tint = agentTint(connection.provider);
            return (
              <span
                className="agents-conn-tile"
                style={{ background: tint.bg, color: tint.color }}
                title={tint.full}
                key={connection.id}>
                <ChannelGlyph provider={connection.provider} size={14} />
                {connection.status === "ERROR" && <i />}
              </span>
            );
          })
        )}
      </div>
      <div className="agents-row-open" style={{ color: open ? "var(--warning-text)" : "var(--n-5)" }}>
        {open || "—"}
      </div>
      <Dropdown
        menu={{ items: menuItems }}
        open={menuOpen}
        onOpenChange={setMenuOpen}
        trigger={["click"]}
        overlayClassName="app-dropdown">
        <button
          className="agents-row-menu row-menu-button"
          type="button"
          aria-label={t("ai.agent_actions")}
          title={t("common.actions")}
          onClick={(event) => event.stopPropagation()}>
          <Icon name="more" size={16} strokeWidth={2} />
        </button>
      </Dropdown>
    </div>
  );
}
