import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { t } from "../../i18n";
import { fetchRatingSettings, saveRatingSettings, type RatingSettings } from "./api";
import { ratingSettingsDraft, ratingSettingsInput } from "./settingsModel";

export function useRatingSettings() {
  const [saved, setSaved] = useState<RatingSettings | null>(null);
  const [draft, setDraft] = useState<RatingSettings | null>(null);
  const [minutes, setMinutes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [invalidScale, setInvalidScale] = useState(false);
  function accept(value: RatingSettings) {
    const next = ratingSettingsDraft(value);
    setSaved(value);
    setDraft(next);
    setMinutes(String(next.delaySeconds / 60));
  }
  useEffect(() => {
    let active = true;
    fetchRatingSettings().then(value => { if (active) accept(value); })
      .catch(problem => { if (active) setError(problem instanceof Error ? problem.message : t("common.request_failed")); });
    return () => { active = false; };
  }, []);
  async function save() {
    if (!draft || busy) return;
    const input = ratingSettingsInput(draft, minutes);
    setInvalidScale(input.invalidScale);
    setError(input.error);
    if (input.invalidScale || input.error) return;
    setBusy(true); setError(""); setInvalidScale(false);
    try {
      accept(await saveRatingSettings(input.value));
    } catch (problem) {
      if (problem instanceof ApiError && problem.status === 400 && draft.scale.some(choice => !choice.label.trim())) setInvalidScale(true);
      else setError(problem instanceof Error ? problem.message : t("common.request_failed"));
    } finally { setBusy(false); }
  }
  return { saved, draft, setDraft, minutes, setMinutes, busy, error, invalidScale, save };
}
