import { t } from "../../i18n";
import { visibleOnboardingSteps, type OnboardingStep } from "./steps";

export function operationModeSteps(isInstanceAdmin: boolean, mode?: string): OnboardingStep[] {
  const steps = visibleOnboardingSteps(isInstanceAdmin);
  if (mode !== "OPERATORS_ONLY") return steps;
  return steps.filter((step) => !["providerConnected", "agentActive", "knowledgeFilled"].includes(step.key))
    .map((step): OnboardingStep => {
      if (step.key === "connectionBound") return {
        ...step,
        instructions: [...step.instructions.slice(0, 3), t("onboarding.operator_connection"), step.instructions[4]],
        preview: { ...step.preview, rows: step.preview.rows.filter((_, index) => index !== 1) },
      };
      if (step.key !== "firstConversation") return step;
      return {
        ...step,
        lead: t("onboarding.operator_check_lead"),
        instructions: [t("onboarding.operator_check_send"), t("onboarding.operator_check_queue"),
          t("onboarding.operator_check_reply")],
        warning: t("onboarding.operator_check_waiting"),
        preview: { ...step.preview, rows: [step.preview.rows[0], {
          label: t("onboarding.s8.row3_label"), value: t("conversations.waiting_person"),
        }], chip: t("conversations.waiting_person"), tone: "waiting" },
        target: { ...step.target, text: t("onboarding.operator_check_lead") },
      };
    });
}
