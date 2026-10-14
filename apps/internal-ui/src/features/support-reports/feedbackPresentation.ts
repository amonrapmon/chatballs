import { fmt, t } from "../../i18n";
import type { ScoreSummary } from "./feedbackTypes";
import { missing } from "./presentation";

export const feedbackNumber = (value: number | null) => value === null ? missing : fmt.number(value, { maximumFractionDigits: 1 });
export const feedbackRate = (value: number | null) => value === null ? missing : fmt.number(value, { style: "percent", maximumFractionDigits: 0 });

export function scaleLabel(scale: Array<string | number>): string {
  if (scale.length > 1 && scale.every((value, index) => typeof value === "number" && (index === 0 || value === Number(scale[index - 1]) + 1))) {
    return `${fmt.number(Number(scale[0]))}–${fmt.number(Number(scale.at(-1)))}`;
  }
  return scale.map((value) => typeof value === "number" ? fmt.number(value) : value).join(" / ");
}

export function scoreLabel(summary: ScoreSummary): string {
  if (summary.value === null) return missing;
  return summary.kind === "positiveRate" ? t("reports.score_positive", { rate: feedbackRate(summary.value), value: summary.positiveValue ?? "" })
    : feedbackNumber(summary.value);
}

export function versionPeriod(from: string, to: string | null, timezone: string): string {
  const formatter = new Intl.DateTimeFormat(fmt.tag(), { timeZone: timezone, day: "numeric", month: "short" });
  return to ? formatter.formatRange(new Date(from), new Date(Math.max(new Date(from).getTime(), new Date(to).getTime() - 1)))
    : t("reports.version_since", { date: formatter.format(new Date(from)) });
}
