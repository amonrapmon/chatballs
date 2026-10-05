import type { Message } from "@chatballs/shared";
import type { toolCallsRu } from "./tool-calls.ru";

export const toolCallsEn = {
  "tool_calls.requested": "Agent requested {detail}",
  "tool_calls.detail": "“{tool}” · {duration}",
  "tool_calls.failed_detail": "“{tool}” · error: {error}",
  "tool_calls.duration": "{seconds} s",
  "tool_calls.requested_count": { one: "Agent requested {count} tool", other: "Agent requested {count} tools" },
  "tool_calls.error_count": { one: "{count} with an error", other: "{count} with errors" },
} as const satisfies Record<keyof typeof toolCallsRu, Message>;
