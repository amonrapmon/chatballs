import { useCallback, useEffect, useState } from "react";

import { api } from "../../api/client";
import type { Integration } from "./model";

export function useWebIntegration(id: number) {
  const [integration, setIntegration] = useState<Integration | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const reload = useCallback(() => {
    setLoading(true);
    setFailed(false);
    api<{ items: Integration[] }>("/api/v1/integrations/")
      .then(({ items }) => setIntegration(items.find((item) => item.id === id && item.provider === "WEB") ?? null))
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => { reload(); }, [reload]);
  return { integration, loading, failed, reload, setIntegration };
}
