import { Dropdown } from "antd";
import { t, tn, fmt } from "../../i18n";
import { Icon } from "../../shared/icons";
import { Pagination } from "../../shared/Pagination";
import type { Skill } from "./model";
import { SkillGlyph } from "./SkillGlyph";
import type { useSkillsList } from "./useSkillsList";

export function SkillsTable({
  list,
  open,
  remove,
  openAgent,
}: {
  list: ReturnType<typeof useSkillsList>;
  open: (id: string) => void;
  remove: (id: string) => void;
  openAgent: (id: number) => void;
}) {
  return (
    <div className="skills-table">
      <div className="skills-table-head">
        {(["skills.skill", "skills.templates", "skills.agents", "skills.updated"] as const).map((key) => (
          <span key={key}>{t(key)}</span>
        ))}
        <span />
      </div>
      {list.loading ? (
        <div aria-busy="true" aria-label={t("skills.loading")}>
          {[0, 1, 2, 3].map((index) => (
            <div className="skills-table-row skills-skeleton" key={index}>
              <div>
                <i className="skill-skeleton-tile" />
                <span>
                  <i />
                  <i />
                </span>
              </div>
              <i />
              <i />
              <i />
              <span />
            </div>
          ))}
          <footer>{t("skills.loading")}</footer>
        </div>
      ) : (
        <>
          {list.items.map((skill) => (
            <SkillRow
              key={skill.id}
              skill={skill}
              open={() => open(skill.id)}
              remove={() => remove(skill.id)}
              openAgent={openAgent}
            />
          ))}
          <footer>
            <span>
              {tn("skills.total", list.total)} · {tn("skills.used", list.payload?.connectedAgentCount ?? 0)}
            </span>
            <span>{t("skills.managers")}</span>
          </footer>
          {list.pageCount > 1 && <Pagination page={list.page} pageCount={list.pageCount} onPage={list.setPage} />}
        </>
      )}
    </div>
  );
}
function SkillRow({
  skill,
  open,
  remove,
  openAgent,
}: {
  skill: Skill;
  open: () => void;
  remove: () => void;
  openAgent: (id: number) => void;
}) {
  return (
    <div className="skills-table-row">
      <div className="skill-identity">
        <span className="skill-tile">
          <SkillGlyph />
        </span>
        <div>
          <button className="link is-neutral is-strong" onClick={open}>
            {skill.name}
          </button>
          <small>{skill.description}</small>
        </div>
      </div>
      <div className="skill-chips">
        {skill.templates.length ? (
          skill.templates.map((template) => (
            <span className="skill-chip" key={template.id}>
              <Icon name="columns" size={11} />
              {template.name}
            </span>
          ))
        ) : (
          <small>{t("skills.instruction_only")}</small>
        )}
      </div>
      <div className="skill-chips">
        {skill.agents.length ? (
          skill.agents.map((agent) => (
            <button className="link skill-chip is-agent" key={agent.id} onClick={() => openAgent(agent.id)}>
              <Icon name="robot" size={12} />
              {agent.name}
            </button>
          ))
        ) : (
          <small>{t("skills.unattached")}</small>
        )}
      </div>
      <small>
        {fmt.shortDateTime(skill.updatedAt)}
        <br />
        {skill.updatedBy?.name}
      </small>
      <Dropdown
        trigger={["click"]}
        overlayClassName="app-dropdown"
        menu={{
          items: [
            { key: "edit", label: t("common.edit"), onClick: open },
            { key: "delete", label: t("common.delete"), danger: true, onClick: remove },
          ],
        }}>
        <button className="row-menu-button" aria-label={t("common.actions")}>
          <Icon name="more" size={16} />
        </button>
      </Dropdown>
    </div>
  );
}
