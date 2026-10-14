import type { QualityCriterion, QualitySettings, QualityValue } from "./types";

/** Suggestions are local editor input, never a saved or enabled configuration. */
export function suggestedCriteria(saved: QualitySettings): QualityCriterion[] | null {
  if (saved.criteriaVersion !== null || saved.criteria.length) return null;
  return saved.suggestedCriteria?.map(item => ({ ...item, scale: [...item.scale],
    ...(item.reporting ? { reporting: { ...item.reporting } } : {}) })) ?? null;
}

export function changeCriterionScale(item: QualityCriterion, values: QualityValue[]): QualityCriterion {
  const { reporting, ...criterion } = item;
  const keepReporting = reporting && values.length === 2 && values.every(value => typeof value === "string")
    && values.includes(reporting.positiveValue);
  return { ...criterion, scale: [...values], ...(keepReporting ? { reporting } : {}) };
}
