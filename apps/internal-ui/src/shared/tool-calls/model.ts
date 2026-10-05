import { fmt, t } from "../../i18n";

/** Shared with conversation events and the agent test-chat response. */
export type ToolCall = {
  tool: string;
  ok: boolean;
  error: string;
  durationMs: number;
};

export function toolDuration(durationMs: number): string {
  return t("tool_calls.duration", {
    seconds: fmt.number(durationMs / 1000, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
  });
}

export function toolCallDetail(call: ToolCall): string {
  return call.ok
    ? t("tool_calls.detail", { tool: call.tool, duration: toolDuration(call.durationMs) })
    : t("tool_calls.failed_detail", { tool: call.tool, error: call.error });
}
