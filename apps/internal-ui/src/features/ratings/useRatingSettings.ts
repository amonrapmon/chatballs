import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { t } from "../../i18n";
import { fetchRatingSettings, saveRatingSettings, type RatingSettings } from "./api";

export function useRatingSettings() {
  const [saved, setSaved] = useState<RatingSettings | null>(null);
  const [draft, setDraft] = useState<RatingSettings | null>(null);
  const [minutes, setMinutes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [invalidScale, setInvalidScale] = useState(false);
  function accept(value: RatingSettings) {
    setSaved(value);
    setDraft({ ...value, scale: value.scale.length ? value.scale : Array.from({ length: 5 }, (_, i) => ({ value: i + 1, label: "" })) });
    setMinutes(String(value.delaySeconds / 60));
  }
  useEffect(() => {
    let active = true;
    fetchRatingSettings().then(value => { if (active) accept(value); })
      .catch(problem => { if (active) setError(problem instanceof Error ? problem.message : t("common.request_failed")); });
    return () => { active = false; };
  }, []);
  async function save() {
    if (!draft || busy) return;
    setBusy(true); setError(""); setInvalidScale(false);
    try {
      const scale = !draft.enabled && draft.scale.every(choice => !choice.label) ? [] : draft.scale;
      accept(await saveRatingSettings({ enabled: draft.enabled, scale, text: draft.text, delaySeconds: minutes.trim() ? Number(minutes) * 60 : NaN }));
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 400 && draft.scale.some(choice => !choice.label.trim())) setInvalidScale(true);
      else setError(problem instanceof Error ? problem.message : t("common.request_failed"));
    } finally { setBusy(false); }
  }
  return { saved, draft, setDraft, minutes, setMinutes, busy, error, invalidScale, save };
}
