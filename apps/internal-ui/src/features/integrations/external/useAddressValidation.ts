import { useEffect, useState } from "react";
import { api } from "../../../api/client";
import { t } from "../../../i18n";
import type { FieldErrors } from "./types";

// DNS и настройку локальной сети проверяет тот же сервер, что при сохранении.
export function useAddressValidation(url: string, enabled: boolean) {
  const [result, setResult] = useState<{ url: string; errors: FieldErrors } | null>(null);
  const checking = enabled && Boolean(url.trim()) && result?.url !== url;
  useEffect(() => {
    if (!enabled || !url.trim()) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void api<{ errors: FieldErrors }>("/api/v1/integrations/http/validate-address/", {
        method: "POST", body: JSON.stringify({ url }), signal: controller.signal,
      }).then(({ errors }) => {
        if (!controller.signal.aborted) setResult({ url, errors });
      }).catch(() => {
        if (!controller.signal.aborted) setResult({ url, errors: { url: [t("common.request_failed")] } });
      });
    }, 400);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [url, enabled]);
  return { checking, errors: enabled && result?.url === url ? result.errors : {} };
}
