import { Icon } from "../../shared/icons";
import { t } from "../../i18n";

/** idle — можно запросить; active — панель открыта; busy — готовится; off — выключено у агента. */
export type DraftButtonState = "idle" | "active" | "busy" | "off";

// Кнопка «Черновик AI» в панели инструментов редактора (кадры A1–A5, A8, A10).
// Запрос не трогает текст в поле и ничего не отправляет.
export function ComposerDraftButton({ state, agentName, onRequest }: { state: DraftButtonState; agentName: string; onRequest: () => void }) {
  const title = {
    idle: t("conversations.draft_request"),
    active: t("conversations.draft_open"),
    busy: t("conversations.draft_in_progress"),
    off: agentName ? t("conversations.draft_disabled_for_agent", { name: agentName }) : t("conversations.draft_agent_required"),
  }[state];
  return (
    <button
      className={`composer-tool is-labeled is-ai is-${state}`}
      title={title}
      type="button"
      // Недоступная кнопка остаётся видимой и объясняет причину подсказкой.
      aria-disabled={state === "off" || state === "busy"}
      onClick={state === "idle" ? onRequest : undefined}
    >
      <Icon name="sparkles" size={16} />{state === "busy" ? t("conversations.draft_preparing_short") : t("conversations.ai_draft")}
    </button>
  );
}
