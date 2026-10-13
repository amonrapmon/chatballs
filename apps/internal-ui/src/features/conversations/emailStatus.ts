import type { EmailOperation, EmailState } from "./emailTypes";

export function emailState(operation: EmailOperation): EmailState {
  if (operation.attempts.some((attempt) => attempt.state === "SMTP_ACCEPTED")) return "SMTP_ACCEPTED";
  const latest = [...operation.attempts].sort((a, b) => b.number - a.number)[0];
  if (!latest) return "PENDING";
  if (latest.state === "FAILED" && operation.attempts.some((attempt) => attempt.state === "UNKNOWN")) return "UNKNOWN";
  return latest.state;
}
// Ожидающая попытка ещё не началась и в счётчик не идёт.
export const startedAttempts = (operation: EmailOperation) => operation.attempts.filter((attempt) => attempt.state !== "PENDING").length;
// Причина рядом со статусом; у неизвестного результата — причина той попытки, чей исход неизвестен.
export function emailReason(operation: EmailOperation, state: EmailState) {
  const rows = [...operation.attempts].sort((a, b) => b.number - a.number);
  return (state === "UNKNOWN" ? rows.find((attempt) => attempt.state === "UNKNOWN") : rows[0])?.errorMessage ?? "";
}
export const emailStatusKeys = { PENDING: "mail.pending", SENDING: "mail.sending", SMTP_ACCEPTED: "mail.accepted", FAILED: "mail.failed", UNKNOWN: "mail.unknown" } as const;
export const emailStatusIcons = { PENDING: "clock", SENDING: "refresh", SMTP_ACCEPTED: "check", FAILED: "close", UNKNOWN: "info" } as const;
export const emailTone = { PENDING: "neutral", SENDING: "accent", SMTP_ACCEPTED: "success", FAILED: "error", UNKNOWN: "warning" } as const;
