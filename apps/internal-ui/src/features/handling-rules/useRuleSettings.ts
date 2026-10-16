import { useEffect, useState } from "react";
import { fetchRules, patchRule } from "./api";
import { changesFor, ruleErrors, validateRule } from "./model";
import type { HandlingRule, RuleErrors, RuleKind } from "./types";

export function useRuleSettings() {
  const [saved, setSaved] = useState<HandlingRule[]>([]);
  const [draft, setDraft] = useState<HandlingRule[]>([]);
  const [errors, setErrors] = useState<Partial<Record<RuleKind, RuleErrors>>>({});
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    fetchRules(controller.signal).then(({ items }) => { setSaved(items); setDraft(items); })
      .catch(problem => { if (!controller.signal.aborted) setLoadError(ruleErrors(problem).detail ?? ""); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);
  function change(value: HandlingRule) {
    setDraft(items => items.map(item => item.kind === value.kind ? value : item));
    setErrors(items => ({ ...items, [value.kind]: undefined }));
  }
  async function save() {
    if (busy) return;
    const changed = draft.filter(item => Object.keys(changesFor(saved.find(value => value.kind === item.kind)!, item)).length);
    const invalid = Object.fromEntries(changed.map(item => [item.kind, validateRule(item)]).filter(([, value]) => Object.keys(value).length));
    setErrors(invalid);
    if (Object.keys(invalid).length) return;
    setBusy(true);
    try {
      for (const item of changed) {
        try {
          const { rule } = await patchRule(item.kind, changesFor(saved.find(value => value.kind === item.kind)!, item));
          setSaved(items => items.map(value => value.kind === rule.kind ? rule : value));
          setDraft(items => items.map(value => value.kind === rule.kind ? rule : value));
        } catch (problem) { setErrors(items => ({ ...items, [item.kind]: ruleErrors(problem) })); }
      }
    } finally { setBusy(false); }
  }
  return { saved, draft, errors, loadError, busy, loading, change, save };
}
