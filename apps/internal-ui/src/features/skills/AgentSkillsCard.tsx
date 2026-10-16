import { useState } from "react";
import { t, tn } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import { ErrorScreen, LoadingState, PermissionScreen } from "../../shared/ui";
import { Pagination } from "../../shared/Pagination";
import { SkillGlyph } from "./SkillGlyph";
import type { AgentCard } from "../agents/model";
import type { Skill } from "./model";
import { useSkillsList } from "./useSkillsList";
import { SkillPicker } from "./SkillPicker";
import { SkillDisconnectDialog } from "./SkillDisconnectDialog";
import { SkillsModelWarning } from "./SkillsModelWarning";
import "./styles";
export function AgentSkillsCard({ card }: { card: AgentCard }) {
  const list = useSkillsList("", String(card.id));
  const [picking, setPicking] = useState(false);
  const [disconnecting, setDisconnecting] = useState<Skill | null>(null);
  const libraryPath = window.location.pathname.replace(/\/agents\/\d+\/?$/, "/agents/skills");
  return (
    <section className="agent-card agent-skills-card">
      <header className="skill-section-head">
        <div>
          <h3>{t("skills.title")}</h3>
          <p>{t("skills.card_hint")}</p>
        </div>
        <Button variant="secondary" icon="plus" onClick={() => setPicking(true)}>
          {t("skills.connect")}
        </Button>
      </header>
      {list.forbidden ? (
        <PermissionScreen onReturn={() => window.history.back()} />
      ) : list.errorText ? (
        <ErrorScreen retry={() => void list.reload()} />
      ) : list.loading ? (
        <LoadingState variant="inline" />
      ) : !list.total ? (
        <p>{t("skills.none")}</p>
      ) : (
        list.items.map((skill) => (
          <div className="agent-skill" key={skill.id}>
            <span className="skill-tile">
              <SkillGlyph />
            </span>
            <div>
              <strong>{skill.name}</strong>
              <small>{skill.description}</small>
              <small>
                {skill.templateCount ? tn("skills.template_count", skill.templateCount) : t("skills.instruction_only")}{" "}
                · {tn("skills.used", skill.agentCount)}
              </small>
            </div>
            <a className="link has-icon" href={`${libraryPath}?skill=${skill.id}`}>
              {t("skills.library")}
            </a>
            <Button variant="secondary" onClick={() => setDisconnecting(skill)}>
              {t("skills.disconnect")}
            </Button>
          </div>
        ))
      )}
      {list.pageCount > 1 && <Pagination page={list.page} pageCount={list.pageCount} onPage={list.setPage} />}
      <SkillsModelWarning support={card.modelSupportsTools} />
      <div className="skill-notice">{t("skills.shared_hint", { name: card.name })}</div>
      {picking && (
        <SkillPicker
          agentId={card.id}
          name={card.name}
          close={() => setPicking(false)}
          changed={() => void list.reload()}
        />
      )}
      {disconnecting && (
        <SkillDisconnectDialog
          initial={disconnecting}
          agentId={card.id}
          name={card.name}
          close={() => setDisconnecting(null)}
          changed={() => void list.reload()}
        />
      )}
    </section>
  );
}
