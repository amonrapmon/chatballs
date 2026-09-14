import { Icon } from "../../shared/icons";
import { pickedInGroup, type ChoiceGroup } from "./agentKnowledgeGroups";
import { t } from "../../i18n";

// Одна категория (или портал) в диалоге «Знания» карточки агента: заголовок со
// счётчиком выбранного, «выбрать все» и список материалов.

export function AgentKnowledgeGroup({ group, picked, open, onToggleOpen, onToggleChoice, onToggleAll }: {
  group: ChoiceGroup;
  picked: ReadonlySet<string>;
  open: boolean;
  onToggleOpen: () => void;
  onToggleChoice: (key: string) => void;
  onToggleAll: (keys: string[], pick: boolean) => void;
}) {
  const inGroup = pickedInGroup(group, picked);
  const allPicked = inGroup === group.choices.length;
  return (
    <div className="agent-knowledge-group">
      <div className="agent-knowledge-group-head">
        <button
          aria-expanded={open}
          className={`agent-knowledge-group-toggle${open ? " is-open" : ""}`}
          type="button"
          onClick={onToggleOpen}
        >
          <Icon name="chevronRight" size={13} strokeWidth={2.2} />
          <Icon name={group.icon} size={14} strokeWidth={1.8} />
          <strong>{group.title}</strong>
          <small>{inGroup > 0 ? `${inGroup} / ${group.choices.length}` : group.choices.length}</small>
        </button>
        <button
          className="link is-muted"
          type="button"
          onClick={() => onToggleAll(group.choices.map((choice) => choice.key), !allPicked)}
        >
          {allPicked ? t("ai.clear_selection") : t("ai.select_all")}
        </button>
      </div>
      {open && group.choices.map((choice) => (
        <label className={`agent-knowledge-choice ${picked.has(choice.key) ? "is-picked" : ""}`} key={choice.key}>
          <input type="checkbox" checked={picked.has(choice.key)} onChange={() => onToggleChoice(choice.key)} />
          <strong>{choice.title}</strong>
          <small>{choice.meta}</small>
        </label>
      ))}
    </div>
  );
}
