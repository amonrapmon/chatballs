import { useState } from "react";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { linkKnowledgeToAgent, linkPortalArticlesToAgent } from "../ai/knowledge/api";
import { AgentKnowledgeDialog } from "./AgentKnowledgeDialog";
import { knowledgeRows, knowledgeLine, patchAgent, type AgentCard } from "./model";

// --- Знания (кадры G3/G4/G5) ---

export function KnowledgeCard({ card, canManage, openKnowledge, reload }: {
  card: AgentCard;
  canManage: boolean;
  openKnowledge: (knowledgeId: number) => void;
  reload: () => void;
}) {
  const [picking, setPicking] = useState(false);
  const rows = knowledgeRows(card);

  async function detach(kind: "knowledge" | "article", id: number) {
    if (kind === "knowledge") await linkKnowledgeToAgent({ agentId: card.aiAgentId, action: "detach", knowledgeIds: [id] });
    else await linkPortalArticlesToAgent({ agentId: card.aiAgentId, action: "detach", articleIds: [id] });
    reload();
  }

  return (
    <section className="agent-card">
      <div className="agent-card-head is-row">
        <div><h3>{t("ai.knowledge")}</h3><small>{knowledgeLine(card)}</small></div>
        {canManage && (
          <button className="agent-inline-button" type="button" onClick={() => setPicking(true)}>
            <Icon name="plus" size={13} strokeWidth={2.2} />{t("ai.select")}</button>
        )}
      </div>
      {rows.length === 0 ? (
        <p className="agent-knowledge-empty">{t("ai.no_knowledge_attached_so_agent")}</p>
      ) : (
        <div className="agent-knowledge-list">
          {rows.map((row) => (
            <div className="agent-knowledge-row" key={row.key}>
              <Icon name={row.icon} size={15} strokeWidth={1.9} />
              {row.kind === "knowledge"
                ? <button className="agent-knowledge-title" type="button" onClick={() => openKnowledge(row.id)}>{row.title}</button>
                : <a className="agent-knowledge-title" href={row.href} rel="noreferrer" target="_blank">{row.title}</a>}
              {row.chip && <small className={`agent-chip is-${row.chipTone}`}>{row.chip}</small>}
              <small className="agent-knowledge-meta">{row.meta}</small>
              {canManage && (
                <button className="agent-knowledge-remove" type="button" aria-label={t("common.remove")} title={t("common.remove")} onClick={() => void detach(row.kind, row.id)}>
                  <Icon name="close" size={12} strokeWidth={2.4} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
      {picking && (
        <AgentKnowledgeDialog
          card={card}
          onClose={() => setPicking(false)}
          onSave={async ({ knowledgeIds, articleIds }) => {
            await patchAgent(card.id, { knowledgeIds });
            const current = card.portalArticles.map((article) => article.id);
            const attach = articleIds.filter((id) => !current.includes(id));
            const detachIds = current.filter((id) => !articleIds.includes(id));
            if (attach.length) await linkPortalArticlesToAgent({ agentId: card.aiAgentId, action: "attach", articleIds: attach });
            if (detachIds.length) await linkPortalArticlesToAgent({ agentId: card.aiAgentId, action: "detach", articleIds: detachIds });
            reload();
          }}
        />
      )}
    </section>
  );
}
