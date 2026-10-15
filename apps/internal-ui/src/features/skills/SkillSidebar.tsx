import { t, tn } from "../../i18n";
import { Icon } from "../../shared/icons";
import type { Skill } from "./model";
export function SkillSidebar({ skill, openAgent }: { skill: Skill | null; openAgent: (id: number) => void }) {
  return (
    <div className="skill-column">
      <section className="skill-panel">
        <h3>{t("skills.agents")}</h3>
        <p>{t("skills.connect_hint")}</p>
        {skill?.agents.length ? (
          <>
            {skill.agents.map((agent) => (
              <div className="skill-agent" key={agent.id}>
                <Icon name="robot" size={16} />
                <button className="link is-neutral is-strong" onClick={() => openAgent(agent.id)}>
                  {agent.name}
                </button>
                <Icon name="chevronRight" size={14} />
              </div>
            ))}
            <div className="skill-notice is-warning">
              <Icon name="warning" size={14} />
              <span>{tn("skills.affected", skill.agentCount)}</span>
            </div>
          </>
        ) : (
          <p>{t("skills.no_agents")}</p>
        )}
      </section>
      <section className="skill-panel">
        <h3>{t("skills.bounds")}</h3>
        {(
          [
            ["shield", "skills.bounds_rights"],
            ["lock", "skills.bounds_style"],
            ["clock", "skills.bounds_history"],
          ] as const
        ).map(([icon, key]) => (
          <div className="skill-bound" key={key}>
            <Icon name={icon} size={15} />
            <span>{t(key)}</span>
          </div>
        ))}
      </section>
    </div>
  );
}
