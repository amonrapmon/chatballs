import { useState } from "react";
import { api, ApiError } from "../../../api/client";
import { t } from "../../../i18n";
import type { Integration } from "../model";
import { serverDraft } from "./model";
import { draftErrors } from "./validation";
import type { FieldErrors, ServerDraft, ServerKind } from "./types";

export function useServerEditor(kind: ServerKind, initial: Integration | null, onCreated: (id: number) => void) {
  const [integration, setIntegration] = useState(initial);
  const [draft, setDraft] = useState(() => serverDraft(kind, initial));
  const [serverErrors, setServerErrors] = useState<FieldErrors>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [saved, setSaved] = useState(false);
  const errors = { ...serverErrors, ...draftErrors(draft) };
  const dirty = JSON.stringify(draft) !== JSON.stringify(serverDraft(kind, integration));

  function change(next: ServerDraft) { setDraft(next); setServerErrors({}); setError(""); setSaved(false); }
  function accept(next: Integration, resetDraft = false) {
    setIntegration(next);
    if (resetDraft) setDraft(serverDraft(kind, next));
  }
  function fail(caught: unknown) {
    if (caught instanceof ApiError && caught.status === 400) {
      const fields = (caught.payload.errors as FieldErrors | undefined) ?? {};
      setServerErrors(fields);
      setError(Object.keys(fields).length ? "" : caught.message);
    } else setError(t("common.request_failed"));
  }
  async function save() {
    if (Object.keys(errors).length || busy) return;
    setBusy(true); setSaving(true); setError("");
    const { tools: _tools, toolsState: _state, toolsRefreshedAt: _refreshed, ...settings } = draft.externalServer;
    try {
      const { integration: next } = await api<{ integration: Integration }>(
        integration ? `/api/v1/integrations/${integration.id}/` : "/api/v1/integrations/", {
          method: integration ? "PATCH" : "POST",
          body: JSON.stringify({ provider: kind.toUpperCase(), name: draft.name, isActive: draft.isActive,
            externalServer: { ...settings, headers: settings.headers.map(({ saved: _saved, ...h }) => h) } }),
        });
      accept(next, true); setSaved(true);
      if (!integration) onCreated(next.id);
    } catch (caught) { fail(caught); } finally { setBusy(false); setSaving(false); }
  }
  async function action(path: string, body?: object) {
    if (!integration || busy) return;
    setBusy(true); setSaved(false); setError("");
    if (path === "tools/refresh/") setRefreshing(true);
    try {
      const result = await api<{ integration: Integration }>(`/api/v1/integrations/${integration.id}/${path}`, {
        method: "POST", ...(body ? { body: JSON.stringify(body) } : {}),
      });
      accept(result.integration);
      return true;
    } catch (caught) { fail(caught); return false; } finally { setBusy(false); setRefreshing(false); }
  }
  return { integration, draft, change, errors, error, busy, saving, refreshing, dirty, saved, save, action };
}
export type ServerEditor = ReturnType<typeof useServerEditor>;
