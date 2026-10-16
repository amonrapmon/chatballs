import { t } from "../../i18n";
import { UnderlineTabs } from "../../shared/ui-controls";
export function SkillsTabs({
  skills,
  change,
  count,
  agentCount,
}: {
  skills: boolean;
  change: (skills: boolean) => void;
  count?: number;
  agentCount?: number;
}) {
  return (
    <UnderlineTabs
      className="skills-tabs"
      value={skills ? "skills" : "agents"}
      onChange={(value) => {
        if ((value === "skills") !== skills) change(value === "skills");
      }}
      items={[
        { key: "agents", label: t("skills.agent_list"), count: agentCount },
        { key: "skills", label: t("skills.title"), count },
      ]}
    />
  );
}
