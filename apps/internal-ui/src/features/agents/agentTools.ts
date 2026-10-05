// Блок «Инструменты» карточки агента («Агенты Baseline», кадры G3–G6, G9):
// внешние серверы организации, их инструменты и что из них включено агенту.
import { api } from "../../api/client";
import { fmt, t } from "../../i18n";

export type AgentTool = {
  name: string;
  title: string;
  description: string;
  /** Включить можно только инструмент, который читает. */
  readOnly: boolean;
  enabled: boolean;
};

export type AgentToolServer = {
  integrationId: number;
  name: string;
  type: "mcp" | "http";
  isActive: boolean;
  status: string;
  lastError: string;
  lastErrorCode: string;
  lastCheckedAt: string | null;
  tools: AgentTool[];
};

/** Включённый инструмент в запросе: сервер и имя инструмента на нём. */
export type AgentToolRef = { integrationId: number; name: string };

export function fetchAgentTools(agentId: number): Promise<{ tools: AgentToolServer[] }> {
  return api<{ tools: AgentToolServer[] }>(`/api/v1/agents/${agentId}/tools/`);
}

export type ToolServerState = "ok" | "disabled" | "error";

// Выключенный сервер важнее ошибки: пока он выключен, чинить связь незачем.
export function toolServerState(server: AgentToolServer): ToolServerState {
  if (!server.isActive) return "disabled";
  return server.status === "ERROR" ? "error" : "ok";
}

export function toolServerKind(server: AgentToolServer): string {
  return server.type === "http" ? t("ai.tools_kind_http") : t("ai.tools_kind_mcp");
}

/** Почему группа приглушена; у рабочего сервера причины нет. */
export function toolServerReason(server: AgentToolServer): string {
  const state = toolServerState(server);
  if (state === "ok") return "";
  if (state === "disabled") return t("ai.tools_server_disabled");
  if (server.lastErrorCode === "unreachable" && server.lastCheckedAt) {
    return t("ai.tools_server_unreachable_since", { time: fmt.time(server.lastCheckedAt) });
  }
  return server.lastError;
}

export function enabledToolRefs(servers: AgentToolServer[]): AgentToolRef[] {
  return servers.flatMap((server) =>
    server.tools.filter((tool) => tool.enabled).map((tool) => ({ integrationId: server.integrationId, name: tool.name })),
  );
}

/** Набор включённых после переключения одного инструмента. */
export function toggledToolRefs(servers: AgentToolServer[], integrationId: number, name: string): AgentToolRef[] {
  const current = enabledToolRefs(servers);
  const without = current.filter((ref) => !(ref.integrationId === integrationId && ref.name === name));
  return without.length < current.length ? without : [...current, { integrationId, name }];
}

/** «3 из 6 включены»; если часть включённых стоит на сломанном сервере —
 *  «1 из 3 работает» (кадры G3, G4). */
export function toolsLine(servers: AgentToolServer[]): string {
  const total = servers.reduce((sum, server) => sum + server.tools.length, 0);
  if (total === 0) return "";
  const enabled = enabledToolRefs(servers).length;
  const working = enabledToolRefs(servers.filter((server) => toolServerState(server) === "ok")).length;
  if (working < enabled) return t("ai.tools_working_of", { working, enabled });
  return t("ai.tools_enabled_of", { enabled, total });
}
