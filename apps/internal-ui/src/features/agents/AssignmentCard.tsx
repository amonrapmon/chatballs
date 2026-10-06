import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { SelectField } from "../../shared/form-controls";
import { groupColorOf } from "../conversations/model";
import type { EmployeeGroup } from "../../types";
import type { AgentCard, AgentPatch } from "./model";

// --- Назначение (кадры G3–G5) ---

export function AssignmentCard({ card, groups, canManage, busy, apply }: {
  card: AgentCard;
  groups: EmployeeGroup[];
  canManage: boolean;
  busy: boolean;
  apply: (patch: AgentPatch) => Promise<boolean>;
}) {
  const [name, setName] = useState(card.name);
  useEffect(() => setName(card.name), [card.name]);
  const dirty = name.trim() !== card.name && name.trim().length > 0;

  return (
    <section className="agent-card is-side">
      <h3>{t("ai.assignment")}</h3>
      <p>{t("ai.group_decides_which_operators_see")}</p>
      <div className="agent-side-fields">
        <label className="agent-field">
          <span>{t("common.title")}</span>
          {canManage
            ? <input value={name} onChange={(event) => setName(event.target.value)} onBlur={() => { if (dirty) void apply({ name: name.trim() }); }} />
            : <span className="agent-field-static">{card.name}</span>}
        </label>
        <SelectField
          adornment={<i className="agent-group-dot" style={{ background: card.groupId === null ? "var(--n-5)" : groupColorOf(card.groupId, card.groupColor) }} />}
          disabled={busy}
          label={t("common.group")}
          readOnly={!canManage}
          readOnlyText={card.groupName ?? t("common.no_group")}
          value={card.groupId === null ? "" : String(card.groupId)}
          onChange={(next) => void apply({ groupId: next ? Number(next) : null })}
          options={[["", t("common.no_group")], ...groups.map((group) => [String(group.id), group.name] as [string, string])]}
        />
      </div>
    </section>
  );
}
