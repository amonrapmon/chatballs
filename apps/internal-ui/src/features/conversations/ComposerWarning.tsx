import { TEMPLATE_VARIABLE_LABEL, type unfilledVariables } from "./templateVariables";
import type { ControlMode } from "./types";
import { t } from "../../i18n";

// Кадры A–C: композер активен всегда (решение 2) — первое сообщение
// перехватывает диалог; над полем одна строка-предупреждение.
export function ComposerWarning({ mode, unfilled, internal = false }: { mode: ControlMode; unfilled: ReturnType<typeof unfilledVariables>; internal?: boolean }) {
  const warning = unfilled.length > 0
    ? { color: "var(--warning-text)", dot: "var(--warning)", text: t("conversations.fill_template_variables", { names: unfilled.map((name) => t(TEMPLATE_VARIABLE_LABEL[name]).toLocaleLowerCase()).join(", ") }) }
    : internal ? null : mode === "ai"
      ? { color: "var(--ai)", dot: "var(--ai)", text: t("conversations.ai_handling_conversation_message_takes") }
      : mode === "waiting"
        ? { color: "var(--warning-text)", dot: "var(--warning)", text: t("conversations.customer_waiting_message_assigns_conversation") }
        : null;
  if (!warning) return null;
  return <div className="composer-warning" style={{ color: warning.color }}><i style={{ background: warning.dot }} />{warning.text}</div>;
}
