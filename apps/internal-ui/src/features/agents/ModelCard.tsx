import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { FormField, SelectField } from "../../shared/form-controls";
import { Icon } from "../../shared/icons";
import type { Integration } from "../integrations/model";
import { HISTORY_LIMIT_MAX, type AgentCard, type AgentPatch } from "./model";

// --- Модель (кадры G3–G5) ---

export function ModelCard({ card, providers, canManage, busy, toolsUnsupported, apply }: {
  card: AgentCard;
  providers: Integration[];
  canManage: boolean;
  busy: boolean;
  toolsUnsupported: boolean;
  apply: (patch: AgentPatch) => Promise<boolean>;
}) {
  const missingProvider = card.providerIntegrationId === null;
  const providerName = providers.find((item) => item.id === card.providerIntegrationId)?.name ?? "";
  const transcriptionName = providers.find((item) => item.id === card.transcriptionIntegrationId)?.name ?? "";
  // Поля моделей редактируются свободно и уходят на сервер по потере фокуса:
  // сохранять каждую букву — это запрос на символ.
  const [modelDraft, setModelDraft] = useState(card.model);
  const [transcriptionDraft, setTranscriptionDraft] = useState(card.transcriptionModel);
  useEffect(() => { setModelDraft(card.model); }, [card.model]);
  useEffect(() => { setTranscriptionDraft(card.transcriptionModel); }, [card.transcriptionModel]);
  const [historyDraft, setHistoryDraft] = useState(String(card.historyLimit));
  useEffect(() => { setHistoryDraft(String(card.historyLimit)); }, [card.historyLimit]);
  const historyValue = Number(historyDraft);
  const historyValid = /^\d+$/.test(historyDraft.trim()) && historyValue >= 1 && historyValue <= HISTORY_LIMIT_MAX;

  return (
    <section className="agent-card is-side">
      <h3>{t("common.model")}</h3>
      <p>{t("ai.provider_key_lives_under_settings")}</p>
      <div className="agent-side-fields">
        <SelectField
          disabled={busy}
          invalid={missingProvider}
          label={t("ai.provider")}
          readOnly={!canManage}
          readOnlyText={providerName || t("ai.not_selected")}
          value={card.providerIntegrationId ? String(card.providerIntegrationId) : ""}
          onChange={(next) => void apply({ providerIntegrationId: next ? Number(next) : null })}
          options={[["", t("ai.not_selected")], ...providers.map((item) => [String(item.id), item.name] as [string, string])]}
        />
        {/* Ключ провайдера один на организацию, а агентов на нём несколько:
            модель принадлежит агенту. Пустое поле — «как в интеграции», и
            подсказкой в нём стоит её модель. */}
        <FormField
          disabled={busy || !canManage}
          label={t("common.model")}
          mono
          placeholder={missingProvider ? t("ai.pick_provider") : card.providerModel || t("ai.model_of_integration")}
          value={modelDraft}
          onChange={setModelDraft}
          onBlur={() => { if (modelDraft !== card.model) void apply({ model: modelDraft }); }}
        />
        {toolsUnsupported && (
          <small className="agent-model-warning"><Icon name="warning" size={12} strokeWidth={2.2} />{t("ai.model_cannot_call_tools")}</small>
        )}
        {/* Сколько последних сообщений диалога модель получает вместе с новым.
            Больше — агент помнит длинный разговор, но ответ дороже, а у
            локальной модели с малым окном хвост обрежется на её стороне. */}
        <FormField
          disabled={busy || !canManage}
          error={historyValid ? undefined : t("ai.history_limit_invalid", { max: HISTORY_LIMIT_MAX })}
          label={t("ai.history_limit")}
          type="number"
          value={historyDraft}
          onChange={setHistoryDraft}
          onBlur={() => { if (historyValid && historyValue !== card.historyLimit) void apply({ historyLimit: historyValue }); }}
        />
        {/* Речь в текст умеет не всякая модель, которой агент отвечает: у части
            провайдеров аудио-эндпоинта нет вовсе. Поэтому выбор отдельный. */}
        <SelectField
          disabled={busy}
          label={t("ai.transcription_provider")}
          readOnly={!canManage}
          readOnlyText={transcriptionName || t("ai.same_as_answers")}
          value={card.transcriptionIntegrationId ? String(card.transcriptionIntegrationId) : ""}
          onChange={(next) => void apply({ transcriptionIntegrationId: next ? Number(next) : null })}
          options={[["", t("ai.same_as_answers")], ...providers.map((item) => [String(item.id), item.name] as [string, string])]}
        />
        <FormField
          disabled={busy || !canManage}
          label={t("ai.transcription_model")}
          mono
          placeholder={card.transcriptionProviderModel || t("ai.model_of_integration")}
          value={transcriptionDraft}
          onChange={setTranscriptionDraft}
          onBlur={() => { if (transcriptionDraft !== card.transcriptionModel) void apply({ transcriptionModel: transcriptionDraft }); }}
        />
      </div>
    </section>
  );
}
