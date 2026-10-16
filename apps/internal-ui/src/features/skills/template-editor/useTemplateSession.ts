import { useState } from "react";

/** Raw temporary JSON survives local editor navigation, even while incomplete.
 * Selecting a sample does not change the skill's business configuration.
 */
export function useTemplateSession() {
  const [inputs, setInputs] = useState<Record<string, string[]>>({});
  const [selections, setSelections] = useState<Record<string, number>>({});
  const [dirty, setDirty] = useState(false);
  const [touched, setTouched] = useState<Record<string, Record<string, boolean>>>({});
  return {
    inputs, selections, dirty, touched,
    touch: (id: string, fields: string[]) => setTouched((previous) => ({ ...previous,
      [id]: { ...previous[id], ...Object.fromEntries(fields.map((field) => [field, true])) } })),
    change: (next: Record<string, string[]>) => { setInputs(next); setDirty(true); },
    select: (id: string, index: number) => setSelections((previous) => ({ ...previous, [id]: index })),
    markSaved: () => setDirty(false),
    reset: () => { setInputs({}); setSelections({}); setTouched({}); setDirty(false); },
  };
}
