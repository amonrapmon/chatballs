import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { fetchQualitySettings, saveQualitySettings } from "./api";
import { suggestedCriteria } from "./settingsModel";
import type { QualityCriterion, QualitySettings } from "./types";

export function useQualitySettings() {
  const [saved, setSaved] = useState<QualitySettings | null>(null);
  const [draft, setDraft] = useState<QualityCriterion[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [invalid, setInvalid] = useState(false);
  useEffect(() => {
    let active = true;
    fetchQualitySettings().then(value => { if (active) setSaved(value); }).catch(problem => {
      if (active) setError(problem instanceof Error ? problem.message : t("common.request_failed"));
    });
    return () => { active = false; };
  }, []);
  async function save(enabled: boolean, criteria?: QualityCriterion[]) {
    if (busy || !saved) return;
    if (criteria?.some(item => (item.name !== undefined && !item.name.trim()) || !item.description.trim() || !item.scale.length)) {
      setInvalid(true); return;
    }
    setBusy(true); setError(""); setInvalid(false);
    try { setSaved(await saveQualitySettings(enabled, saved, criteria)); if (criteria !== undefined) setDraft(null); }
    catch (problem) { setError(problem instanceof Error ? problem.message : t("common.request_failed")); }
    finally { setBusy(false); }
  }
  const proposal = saved ? suggestedCriteria(saved) : null;
  return { saved, draft, setDraft, criteria: draft ?? proposal ?? saved?.criteria ?? [],
    pendingCriteria: draft !== null || proposal !== null, busy, error, invalid, save };
}
