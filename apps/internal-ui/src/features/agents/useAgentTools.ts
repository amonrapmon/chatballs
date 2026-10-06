import { useCallback, useEffect, useState } from "react";

import { fetchAgentTools, type AgentToolServer } from "./agentTools";

export type AgentToolsState = {
  /** null — список ещё не пришёл или не загрузился. */
  servers: AgentToolServer[] | null;
  failed: boolean;
  reload: () => void;
  /** Свежий список из ответа на сохранение карточки. */
  adopt: (servers: AgentToolServer[] | undefined) => void;
};

// Список инструментов грузится отдельно от карточки (кадр G9): серверы
// организации не должны задерживать или ронять остальную карточку агента.
export function useAgentTools(agentId: number | null): AgentToolsState {
  const [servers, setServers] = useState<AgentToolServer[] | null>(null);
  const [failed, setFailed] = useState(false);

  const reload = useCallback(() => {
    if (!agentId) return;
    setFailed(false);
    setServers(null);
    fetchAgentTools(agentId)
      .then((payload) => setServers(payload.tools))
      .catch(() => setFailed(true));
  }, [agentId]);

  useEffect(() => { reload(); }, [reload]);

  const adopt = useCallback((next: AgentToolServer[] | undefined) => {
    if (!next) return;
    setFailed(false);
    setServers(next);
  }, []);

  return { servers, failed, reload, adopt };
}
