import { Icon } from "../../shared/icons";
import type { EmployeeGroup } from "../../types";
import { groupColorOf } from "../conversations/model";
import { tn } from "../../i18n";

export function EmployeeGroupPicks({ groups, selected, disabled, onChange, counts }: {
  groups: EmployeeGroup[]; selected: number[]; disabled: boolean;
  onChange: (ids: number[]) => void; counts?: Map<number, number>;
}) {
  return <div className="employee-group-picks">
    {groups.map((group) => {
      const active = selected.includes(group.id);
      const count = counts?.get(group.id);
      return <button className={`employee-group-pick ${active ? "is-on" : ""}`} type="button" aria-pressed={active} disabled={disabled}
        onClick={() => onChange(active ? selected.filter((id) => id !== group.id) : [...selected, group.id])} key={group.id}>
        <i>{active && <Icon name="check" size={11} strokeWidth={3} />}</i>
        <span><strong><i className="employee-group-dot" style={{ background: groupColorOf(group.id, group.color) }} />{group.name}</strong>
          <small>{tn("supervision.member_count", group.memberCount, { count: group.memberCount })}{count != null && ` · ${tn("supervision.dialog_count", count, { count })}`}</small>
        </span>
      </button>;
    })}
  </div>;
}
