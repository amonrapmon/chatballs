import { t } from "../../i18n";
import type { RatingSettings } from "./api";

export function ratingSettingsDraft(value: RatingSettings): RatingSettings {
  const empty = !value.enabled && !value.scale.length && !value.text && value.delaySeconds === 0;
  const draft = empty && value.defaults ? { ...value, ...value.defaults } : value;
  return { ...draft, scale: draft.scale.length
    ? draft.scale.map(choice => ({ ...choice }))
    : Array.from({ length: 5 }, (_, index) => ({ value: index + 1, label: "" })),
  };
}

export function ratingSettingsInput(draft: RatingSettings, minutes: string) {
  const delay = Number(minutes) * 60;
  const delaySeconds = Math.round(delay);
  const scale = !draft.enabled && draft.scale.every(choice => !choice.label.trim()) ? [] : draft.scale;
  const invalidScale = (draft.enabled || scale.length > 0)
    && (scale.length !== 5 || scale.some(choice => !choice.label.trim()));
  let error = "";
  if (!minutes.trim() || !Number.isSafeInteger(delaySeconds)
    || delaySeconds < 0 || delaySeconds > 604800 || Math.abs(delay - delaySeconds) > 1e-8) {
    error = t("ratings.delay_invalid");
  } else if (draft.enabled && !draft.text.trim()) {
    error = t("ratings.text_required");
  }
  return { invalidScale, error, value: {
    enabled: draft.enabled, scale, text: draft.text, delaySeconds,
  } };
}
