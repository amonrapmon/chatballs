import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { setPreLoginLanguage, tn } from "../../i18n";
import { ToolCallChip } from "./ToolCallChip";
import { toolCallDetail, type ToolCall } from "./model";

const call: ToolCall = { tool: "Статус заказа", ok: true, error: "", durationMs: 400 };
const createdAt = "2026-10-05T17:02:00";
const render = (calls: ToolCall[]) => renderToStaticMarkup(<ToolCallChip calls={calls} createdAt={createdAt} />);
afterEach(() => setPreLoginLanguage("ru"));

describe("ToolCallChip", () => {
  it("renders the single call with duration and time from frame T", () => {
    const html = render([call]);
    expect(html).toContain("Агент запросил «Статус заказа» · 0,4 с · 17:02");
    expect(html).not.toContain("<button");
  });

  it("sums durations and offers disclosure for multiple calls", () => {
    const html = render([{ ...call, durationMs: 500 }, { ...call, tool: "Статус доставки", durationMs: 600 }]);
    expect(html).toContain("Агент запросил 2 инструмента · 1,1 с · 17:02");
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain("tool-call-list");
  });

  it("uses the translated error and marks both single and grouped errors", () => {
    const failed = { ...call, tool: "Свободные окна примерки", ok: false, error: "сервер не ответил", durationMs: 2000 };
    const single = render([failed]);
    expect(single).toContain("is-error");
    expect(single).toContain("Агент запросил «Свободные окна примерки» · ошибка: сервер не ответил · 17:02");
    const group = render([{ ...call, durationMs: 300 }, failed]);
    expect(group).toContain("is-group is-error");
    expect(group).toContain("Агент запросил 2 инструмента · 1 с ошибкой · 2,3 с");
    expect(toolCallDetail(failed)).toBe("«Свободные окна примерки» · ошибка: сервер не ответил");
  });

  it("selects Russian plural forms through tn and formats English durations", () => {
    expect(tn("tool_calls.requested_count", 5)).toBe("Агент запросил 5 инструментов");
    expect(tn("tool_calls.requested_count", 21)).toBe("Агент запросил 21 инструмент");
    setPreLoginLanguage("en");
    expect(render([call])).toContain("Agent requested “Статус заказа” · 0.4 s · 17:02");
    expect(render([call, call])).toContain("Agent requested 2 tools · 0.8 s");
  });
});
