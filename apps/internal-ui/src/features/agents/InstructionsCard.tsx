import { useEffect, useState } from "react";
import { LANGUAGES } from "@chatballs/shared";
import { t } from "../../i18n";
import type { AgentCard, AgentPatch } from "./model";

// --- Инструкции (кадры G3/G5) ---

const INSTRUCTION_FIELDS = [
  { key: "persona", label: t("ai.who_what_does"), hint: t("ai.persona"), rows: 7, placeholder: "" },
  { key: "tone", label: t("ai.how_should_speak"), hint: t("ai.tone"), rows: 7, placeholder: t("ai.example_calmly_politely_formal_address") },
  { key: "instructions", label: t("ai.working_rules"), hint: t("ai.instructions"), rows: 10, placeholder: t("ai.example_do_not_quote_prices") },
] as const;

// Язык ответов клиенту (кадр G3). «Как у клиента» стоит первым и выбран по
// умолчанию: язык обращения — сигнал точнее любой настройки, он лежит прямо в
// сообщении. Явный язык нужен тем, кто отвечает ровно на одном независимо от
// того, на каком спросили. Подписи языков не переводятся — свой язык человек
// узнаёт по его собственному имени.
const ANSWER_LANGUAGES: ReadonlyArray<{ value: string; label: string; lang?: string }> = [
  { value: "MIRROR", label: t("ai.answer_language_mirror") },
  { value: "ORGANIZATION", label: t("ai.answer_language_organization") },
  ...LANGUAGES.map((item) => ({ value: item.code, label: item.label, lang: item.code })),
];

function answerLanguageLabel(value: string): string {
  return ANSWER_LANGUAGES.find((option) => option.value === value)?.label ?? value;
}

export function InstructionsCard({ card, canManage, busy, apply }: {
  card: AgentCard;
  canManage: boolean;
  busy: boolean;
  apply: (patch: AgentPatch) => Promise<boolean>;
}) {
  const [draft, setDraft] = useState({ persona: card.persona, tone: card.tone, instructions: card.instructions, answerLanguage: card.answerLanguage });
  useEffect(() => {
    setDraft({ persona: card.persona, tone: card.tone, instructions: card.instructions, answerLanguage: card.answerLanguage });
  }, [card.persona, card.tone, card.instructions, card.answerLanguage]);
  const dirty =
    draft.persona !== card.persona ||
    draft.tone !== card.tone ||
    draft.instructions !== card.instructions ||
    draft.answerLanguage !== card.answerLanguage;

  return (
    <section className="agent-card">
      <div className="agent-card-head">
        <h3>{t("ai.instructions_2")}</h3>
        <small>{t("ai.system_prompt_assembled_from_three")}</small>
      </div>
      <div className="agent-field is-text agent-answer-language">
        <span>{t("ai.answer_language")}<small>{t("ai.answer_language_hint")}</small></span>
        {canManage ? (
          <div className="appearance-theme-options">
            {ANSWER_LANGUAGES.map((option) => (
              <button
                className={draft.answerLanguage === option.value ? "active" : ""}
                key={option.value}
                lang={option.lang}
                type="button"
                onClick={() => setDraft((current) => ({ ...current, answerLanguage: option.value }))}
              >
                {option.label}
              </button>
            ))}
          </div>
        ) : (
          <span className="agent-field-static">{answerLanguageLabel(card.answerLanguage)}</span>
        )}
      </div>
      <div className="agent-instructions">
        {INSTRUCTION_FIELDS.map((field) => (
          <label className={`agent-field is-text is-rows-${field.rows}`} key={field.key}>
            <span>{field.label}<small>{field.hint}</small></span>
            {canManage ? (
              <textarea
                value={draft[field.key]}
                placeholder={field.placeholder}
                onChange={(event) => setDraft((current) => ({ ...current, [field.key]: event.target.value }))}
              />
            ) : (
              <span className="agent-field-static">{card[field.key] || "—"}</span>
            )}
          </label>
        ))}
      </div>
      {canManage && dirty && (
        <div className="agent-dirty">
          <small>{t("ai.there_unsaved_changes_they_take")}</small>
          <button type="button" disabled={busy} onClick={() => setDraft({ persona: card.persona, tone: card.tone, instructions: card.instructions, answerLanguage: card.answerLanguage })}>{t("ai.undo")}</button>
          <button className="is-primary" type="button" disabled={busy} onClick={() => void apply(draft)}>{t("common.save")}</button>
        </div>
      )}
    </section>
  );
}
