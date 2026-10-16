import { ApiError } from "../../api/client";
import { fmt, t } from "../../i18n";
import type { HandlingRule, Recipient, RuleErrors, RuleKind, RuleValues } from "./types";

export const ruleKinds: RuleKind[] = ["RECEIPT_CONFIRMATION", "WAIT_EXCEEDED_NOTICE", "REPLY_REMINDER", "ASSIGNMENT_RETURN"];
export const ruleName = (kind: RuleKind) => t(`handling_rules.kind_${kind}`);
export const recipientName = (recipient: Recipient) => t(`handling_rules.recipient_${recipient}`);

export function changesFor(saved: HandlingRule, draft: HandlingRule): Partial<RuleValues> {
  const changes: Partial<RuleValues> = {};
  for (const field of ["enabled", "delayMinutes", "conditions", "recipients", "text"] as const) {
    if (JSON.stringify(saved[field]) !== JSON.stringify(draft[field])) Object.assign(changes, { [field]: draft[field] });
  }
  return changes;
}

export function validateRule(rule: HandlingRule): RuleErrors {
  const errors: RuleErrors = {};
  if (rule.delayMinutes !== null && (!Number.isInteger(rule.delayMinutes) || rule.delayMinutes < 1 || rule.delayMinutes > rule.catalog.maxDelayMinutes)
      || rule.enabled && rule.delayMinutes === null) errors.delayMinutes = t("handling_rules.delay_range", { limit: fmt.number(rule.catalog.maxDelayMinutes) });
  if (rule.enabled && rule.catalog.recipients.length && !rule.recipients.length) errors.recipients = t("handling_rules.recipients_required");
  if (rule.enabled && rule.catalog.requiresText && !rule.text.trim()) errors.text = t("handling_rules.text_required");
  return errors;
}

export function ruleErrors(problem: unknown): RuleErrors {
  if (problem instanceof ApiError) {
    return Object.fromEntries(Object.entries(problem.payload).map(([key, value]) => [key, Array.isArray(value) ? value.join(" ") : String(value)]));
  }
  return { detail: problem instanceof Error ? problem.message : t("common.request_failed") };
}

export function ruleSummary(rule: HandlingRule): string {
  if (!rule.enabled) return t("ratings.disabled");
  const errors = validateRule(rule);
  if (errors.recipients) return t("handling_rules.recipients_missing");
  const recipients = rule.catalog.requiresText ? t("handling_rules.customer") : rule.recipients.map(recipientName).join(", ");
  return t(`handling_rules.summary_${rule.kind}`, { recipients, minutes: rule.delayMinutes === null ? "—" : fmt.number(rule.delayMinutes) });
}
