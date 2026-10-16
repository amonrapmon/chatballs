import type { QualityCriterion, QualitySettings } from "./types";
import { sameScale } from "./presentation";

/** JSON.parse merges 1 and 1.0; retain server literals for unchanged scales. */
export function serializeCriteria(criteria: QualityCriterion[], saved: Pick<QualitySettings, "criteria" | "criteriaValueLiterals">): string {
  return `[${criteria.map(item => {
    const original = saved.criteria.find(row => row.code === item.code);
    const literals = original && sameScale(original.scale, item.scale) ? saved.criteriaValueLiterals[item.code] : [];
    const scale = `[${item.scale.map((value, index) => literals?.[index] ?? JSON.stringify(value)).join(",")}]`;
    return `${JSON.stringify({ code: item.code, ...(item.name === undefined ? {} : { name: item.name }), description: item.description,
      ...(item.reporting === undefined ? {} : { reporting: item.reporting }) }).slice(0, -1)},"scale":${scale}}`;
  }).join(",")}]`;
}
