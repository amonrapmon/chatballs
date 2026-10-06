import type { Message } from "@chatballs/shared";

export const toolCallsRu = {
  "tool_calls.requested": "Агент запросил {detail}",
  "tool_calls.detail": "«{tool}» · {duration}",
  "tool_calls.failed_detail": "«{tool}» · ошибка: {error}",
  "tool_calls.duration": "{seconds} с",
  "tool_calls.requested_count": {
    one: "Агент запросил {count} инструмент",
    few: "Агент запросил {count} инструмента",
    many: "Агент запросил {count} инструментов",
    other: "Агент запросил {count} инструмента",
  },
  "tool_calls.error_count": {
    one: "{count} с ошибкой",
    few: "{count} с ошибкой",
    many: "{count} с ошибкой",
    other: "{count} с ошибкой",
  },
} as const satisfies Record<string, Message>;
