import type { agentTestRu } from "./agent-test.ru";

export const agentTestEn: Record<keyof typeof agentTestRu, string | Record<string, string>> = {
  "agent_test.open": "Test agent",
  "agent_test.title": "Agent test",
  "agent_test.subtitle": "This conversation does not appear in chats, contacts or statistics",
  "agent_test.restart": "Start over",
  "agent_test.client_data": "Test client data",
  "agent_test.data_summary": "For testing only, never saved",
  "agent_test.data_hint": "These values are only used for testing and are never saved. The agent receives them just like data from a real client: masked values remain masked.",
  "agent_test.custom_source": "Custom fields come from Website data in the “{name}” connection",
  "agent_test.reset_data": "Reset test data",
  "agent_test.placeholder": "Write as a client…",
  "agent_test.phone_placeholder": "+7 (___) ___-__-__",
  "agent_test.agent_name": "AI · {name}",
  "agent_test.more_fields": { one: "{count} more field", other: "{count} more fields" },
};
