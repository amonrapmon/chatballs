import type { agentAssistanceRu } from "./agent-assistance.ru";

export const agentAssistanceEn: Record<keyof typeof agentAssistanceRu, string> = {
  "agent_assistance.title": "Employee assistance",
  "agent_assistance.new_block": "New section",
  "agent_assistance.description": "Reply drafts in the employee editor use this agent’s conversation history and knowledge. The employee reviews the draft and sends it manually.",
  "agent_assistance.drafts": "Reply drafts for employees",
  "agent_assistance.independent": "Independent of whether the agent replies to customers: either can stay on without the other.",
  "agent_assistance.ai_stopped": "Works even now, while the agent is not replying to customers itself.",
  "agent_assistance.autonomous": "Agent replies to customers",
  "agent_assistance.autonomous_description": "Controlled by the “Stop AI” button in the header. Shown for comparison.",
  "agent_assistance.enabled": "Enabled",
  "agent_assistance.disabled": "Disabled",
  "agent_assistance.saving": "Saving…",
  "agent_assistance.save_error": "Could not save: drafts remain {state}. Check your connection and try again.",
  "agent_assistance.remained_enabled": "enabled",
  "agent_assistance.remained_disabled": "disabled",
  "agent_assistance.retry": "Retry",
  "agent_assistance.no_provider": "Drafts are unavailable: this agent has no AI provider selected. Select one in the Model section.",
};
