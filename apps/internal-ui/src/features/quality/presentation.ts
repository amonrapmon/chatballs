import { fmt } from "../../i18n";
import type { QualityCriterion, QualityJob, QualityValue } from "./types";

export const criterionName = (criterion: QualityCriterion) => criterion.name || criterion.description;
export const valueLabel = (value: QualityValue) => typeof value === "number" ? fmt.number(value) : value;
export function scaleLabel(values: QualityValue[]): string {
  const numeric = values.every((value, index) => typeof value === "number" && (!index || value === Number(values[index - 1]) + 1));
  return numeric && values.length > 2 ? `${valueLabel(values[0])}–${valueLabel(values.at(-1)!)}` : values.map(valueLabel).join(" / ");
}
export const sameScale = (a: QualityValue[], b: QualityValue[]) => JSON.stringify(a) === JSON.stringify(b);
export const latestFirst = (jobs: QualityJob[]) => [...jobs].sort((a, b) => b.id - a.id);
export function displayedJob(jobs: QualityJob[], selectedId: number | null): QualityJob | null {
  const ordered = latestFirst(jobs);
  return ordered.find(job => job.id === selectedId) || ordered.find(job => job.state === "SUCCEEDED") || ordered[0] || null;
}
