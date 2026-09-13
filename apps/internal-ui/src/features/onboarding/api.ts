import { api } from "../../api/client";
import { EMPTY_PROGRESS, type OnboardingProgress } from "./steps";

// Состояние онбординга живёт на сервере, а не в localStorage: требование —
// показать визард всем, кто его ещё не закрыл, включая тех, кто работает в
// установке давно. Признак хранится на членстве человека в организации, так
// что у каждого он свой.

export type OnboardingState = {
  steps: OnboardingProgress;
  dismissedAt: string | null;
  completedAt: string | null;
};

export type OnboardingAction = "dismiss" | "complete" | "restart";

const ENDPOINT = "/api/v1/company/onboarding/";

export function fetchOnboarding(): Promise<OnboardingState> {
  return api<OnboardingState>(ENDPOINT);
}

export function postOnboardingAction(action: OnboardingAction): Promise<OnboardingState> {
  return api<OnboardingState>(ENDPOINT, { method: "POST", body: JSON.stringify({ action }) });
}

/** Состояние до первого ответа сервера: визард ещё не показываем. */
export const PENDING_STATE: OnboardingState = {
  steps: EMPTY_PROGRESS,
  dismissedAt: null,
  completedAt: null,
};
