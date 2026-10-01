import { useEffect, useState } from "react";
import { api } from "../../../api/client";
import { t } from "../../../i18n";
import type { Integration } from "../model";
import { availableFields, preChatConfig, readPreChat, selectField, type PreChatDraft } from "./model";

export function usePreChat(integration: Integration, onSaved: (integration: Integration) => void) {
  const [draft, setDraft] = useState(() => readPreChat(integration.config));
  const [customKeys, setCustomKeys] = useState(() => draft.preChat.fields.map(({ key }) => key));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const schema = integration.config.fields ?? [];

  // Другой раздел может удалить своё поле: убираем ссылку и из черновика.
  useEffect(() => {
    setDraft((current) => ({ ...current, preChat: { ...current.preChat, fields: availableFields(current.preChat.fields, integration.config.fields ?? []) } }));
  }, [integration.config]);

  function change(patch: Partial<PreChatDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
    setError("");
  }
  function select(key: string, selected: boolean) {
    change({ preChat: { ...draft.preChat, fields: selectField(draft.preChat.fields, key, selected) } });
  }
  function add(key: string) {
    setCustomKeys((current) => [...new Set([...current, key])]);
    select(key, true);
  }
  async function save() {
    setBusy(true);
    setError("");
    try {
      const { integration: updated } = await api<{ integration: Integration }>(`/api/v1/integrations/${integration.id}/`, {
        method: "PATCH", body: JSON.stringify({ config: preChatConfig(integration.config, draft) }),
      });
      const normalized = readPreChat(updated.config);
      setDraft(normalized);
      onSaved(updated);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("common.could_not_save"));
    } finally {
      setBusy(false);
    }
  }
  return {
    draft, change, select, add, save, busy, error,
    customFields: schema.filter(({ key }) => customKeys.includes(key)),
    remainingFields: schema.filter(({ key }) => !customKeys.includes(key)),
  };
}
