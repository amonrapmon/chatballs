import { useState } from "react";
import { assignSkill, getSkill, isConflict, skillError, type Skill } from "./model";
import { useSkillsList } from "./useSkillsList";

export function useSkillPicker(agentId: number, close: () => void, changed: () => void) {
  const [query, setQuery] = useState("");
  const list = useSkillsList(query);
  const [selected, setSelected] = useState<Record<string, Skill>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const attached = (skill: Skill) => skill.agents.some((agent) => agent.id === agentId);
  async function connect() {
    if (busy) return;
    setBusy(true);
    setError("");
    const remaining = { ...selected };
    try {
      for (const skill of Object.values(selected)) {
        await assignSkill(skill, agentId, true);
        delete remaining[skill.id];
        setSelected({ ...remaining });
        changed();
      }
      close();
    } catch (caught) {
      setError(skillError(caught));
      setConflict(isConflict(caught));
      void list.reload();
    } finally {
      setBusy(false);
    }
  }
  async function reloadSelected() {
    setBusy(true);
    try {
      const latest = await Promise.all(Object.keys(selected).map((id) => getSkill(id)));
      setSelected(
        Object.fromEntries(latest.filter(({ skill }) => !attached(skill)).map(({ skill }) => [skill.id, skill])),
      );
      await list.reload();
      setConflict(false);
      setError("");
      changed();
    } catch (caught) {
      setError(skillError(caught));
    } finally {
      setBusy(false);
    }
  }
  return { query, setQuery, list, selected, setSelected, busy, error, conflict, attached, connect, reloadSelected };
}
