import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import type { Employee, EmployeeGroup } from "../../types";
import { fetchConversationCounters } from "../conversations/model";
import { EmployeeGroupPicks } from "./EmployeeGroupPicks";
import type { EmployeeForm } from "./model";
import "./supervision.css";

// E2–E4: the fixed role is selected in the existing role control (INTEGRATION.md).
export function EmployeeSupervisionCard({ employee, groups, form, onChange }: {
  employee: Employee; groups: EmployeeGroup[]; form: EmployeeForm;
  onChange: (ids: number[]) => void;
}) {
  const [counts, setCounts] = useState<Map<number, number>>();
  useEffect(() => {
    let active = true;
    void fetchConversationCounters().then((data) => {
      if (active) setCounts(new Map(data.groups.map((group) => [group.id, group.count])));
    }).catch(() => undefined);
    return () => { active = false; };
  }, [employee.id]);
  const enabled = form.role === "SUPERVISOR";
  const selected = groups.filter((group) => form.supervisedGroupIds.includes(group.id));
  const outside = selected.filter((group) => !form.groupIds.includes(group.id));
  const names = (items: EmployeeGroup[]) => items.map((group) => `«${group.name}»`).join(", ");
  return <section className="employee-card">
    <h3>{t("supervision.role")}</h3><p>{t("supervision.lead")}</p>
    <EmployeeGroupPicks groups={groups} selected={form.supervisedGroupIds} disabled={!enabled || !employee.permissions?.canChangeSupervisedGroups}
      onChange={onChange} counts={counts} />
    {enabled && <div className={`supervision-note ${selected.length ? "is-info" : "is-warning"}`}>
      <Icon name={selected.length ? "info" : "warning"} size={15} />
      <span>{selected.length ? t("supervision.area_card", { groups: names(selected), outside: outside.length
        ? t("supervision.outside_membership", { groups: names(outside), name: form.fullName }) : "" })
        : t("supervision.empty_card", { name: form.fullName })}</span>
    </div>}
  </section>;
}
