import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
export function SkillsModelWarning({ support }: { support: boolean | null }) {
  if (support === true) return null;
  return (
    <div className="agent-tools-warning">
      <Icon name="warning" size={15} />
      <small>{t(support === false ? "skills.unsupported" : "skills.unknown")}</small>
    </div>
  );
}
