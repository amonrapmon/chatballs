import { useState } from "react";
import { api } from "../../../api/client";
import type { Integration } from "../model";
import { fieldsSaveError, orderedFields, type SiteField } from "./model";

export function useSiteFields(integration: Integration, onSaved: (integration: Integration) => void) {
  const [fields, setFields] = useState(() => orderedFields(integration.config.fields ?? []));
  const [saved, setSaved] = useState(fields);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const dirty = JSON.stringify(fields) !== JSON.stringify(saved);
  function change(next: SiteField[]) {
    setFields(next.map((field, order) => ({ ...field, order })));
    setError(undefined);
  }
  async function save() {
    setBusy(true);
    setError(undefined);
    try {
      const response = await api<{ integration: Integration }>(`/api/v1/integrations/${integration.id}/`, {
        method: "PATCH", body: JSON.stringify({ config: { ...integration.config, fields } }),
      });
      const next = orderedFields(response.integration.config.fields ?? []);
      setFields(next);
      setSaved(next);
      onSaved(response.integration);
    } catch (caught) {
      setError(fieldsSaveError(caught));
    } finally {
      setBusy(false);
    }
  }
  return { fields, change, save, busy, error, dirty };
}
