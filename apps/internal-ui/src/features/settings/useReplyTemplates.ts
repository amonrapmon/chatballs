import { useCallback, useEffect, useState } from "react";

import { fetchReplyTemplates, type ReplyTemplateRef } from "../conversations/model";

// Шаблоны грузятся на весь экран «Настроек», как интеграции: субменю
// показывает их число, а раздел — список.

export type ReplyTemplatesState = {
  items: ReplyTemplateRef[];
  loading: boolean;
  failed: boolean;
  reload: () => void;
};

export function useReplyTemplates(enabled: boolean): ReplyTemplatesState {
  const [items, setItems] = useState<ReplyTemplateRef[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const reload = useCallback(() => {
    if (!enabled) return;
    setFailed(false);
    fetchReplyTemplates()
      .then(setItems)
      .catch(() => setFailed(true))
      .finally(() => setLoading(false));
  }, [enabled]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { items, loading, failed, reload };
}
