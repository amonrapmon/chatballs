import type { ReactNode } from "react";
import { t, tn, fmt } from "../../i18n";
import { Button } from "../../shared/ui-controls";
import { Icon } from "../../shared/icons";
import { SkillGlyph } from "./SkillGlyph";
import type { Skill } from "./model";
export function SkillEditorHeader({
  skill,
  busy,
  remove,
  actions,
}: {
  skill: Skill | null;
  busy: boolean;
  remove: () => void;
  actions: ReactNode;
}) {
  return (
    <header className="skill-editor-header">
      <span className="skill-tile">
        <SkillGlyph size={26} />
      </span>
      <div className="skill-heading">
        <div>
          <h2>{skill?.name ?? t("skills.create")}</h2>
          {skill && (
            <span className="skill-chip is-agent">
              <Icon name="robot" size={12} />
              {tn("skills.used", skill.agentCount)}
            </span>
          )}
        </div>
        {skill && (
          <p>
            {t("skills.updated")} {fmt.shortDateTime(skill.updatedAt)} · {skill.updatedBy?.name} ·{" "}
            {t("skills.created", { date: fmt.shortDate(skill.createdAt) })}
          </p>
        )}
      </div>
      <div className="skill-actions">
        {skill && (
          <Button variant="danger-outline" disabled={busy} icon="trash" onClick={remove}>
            {t("common.delete")}
          </Button>
        )}
        {actions}
      </div>
    </header>
  );
}
