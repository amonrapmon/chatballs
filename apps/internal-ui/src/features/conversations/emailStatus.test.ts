import { expect, it } from "vitest";
import { emailReason, emailState, startedAttempts } from "./emailStatus";
import type { EmailOperation, EmailState } from "./emailTypes";

const operation = (states: EmailState[]) => ({ attempts: states.map((state, index) => ({ state, number: index + 1 })) }) as EmailOperation;
it("does not erase an uncertain earlier send after a failed retry", () => {
  expect(emailState(operation(["UNKNOWN", "FAILED"]))).toBe("UNKNOWN");
  expect(emailState(operation(["UNKNOWN", "PENDING"]))).toBe("PENDING");
  expect(emailState(operation(["UNKNOWN", "SMTP_ACCEPTED"]))).toBe("SMTP_ACCEPTED");
  expect(emailState(operation(["FAILED"]))).toBe("FAILED");
});
it("counts only started attempts and keeps the reason of the uncertain one", () => {
  expect(startedAttempts(operation(["PENDING"]))).toBe(0);
  expect(startedAttempts(operation(["FAILED", "PENDING"]))).toBe(1);
  expect(startedAttempts(operation(["UNKNOWN", "SMTP_ACCEPTED"]))).toBe(2);
  const retried = { attempts: [{ state: "UNKNOWN", number: 1, errorMessage: "interrupted" }, { state: "FAILED", number: 2, errorMessage: "rejected" }] } as EmailOperation;
  expect(emailReason(retried, emailState(retried))).toBe("interrupted");
  expect(emailReason(operation(["PENDING"]), "PENDING")).toBe("");
});
