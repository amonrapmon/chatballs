import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TestChatFeed } from "./TestChatFeed";

describe("test chat tool calls", () => {
  it("places the shared grouped error chip between the client and agent messages", () => {
    const html = renderToStaticMarkup(<TestChatFeed agentName="Support" turns={[{
      message: "Question", reply: "Answer", createdAt: "2026-10-05T17:02:00",
      calls: [{ tool: "Orders", ok: true, error: "", durationMs: 400 },
        { tool: "Delivery", ok: false, error: "сервер не ответил", durationMs: 700 }],
    }]} />);
    expect(html).toContain("tool-call-chip is-group is-error");
    expect(html).toContain("Агент запросил 2 инструмента · 1 с ошибкой · 1,1 с");
    expect(html.indexOf("Question")).toBeLessThan(html.indexOf("tool-call-chip"));
    expect(html.indexOf("tool-call-chip")).toBeLessThan(html.indexOf("Answer"));
  });

  it("retains calls returned with a provider failure", () => {
    const html = renderToStaticMarkup(<TestChatFeed agentName="Support" turns={[{
      message: "Question", error: "Unavailable", createdAt: "2026-10-05T17:02:00",
      calls: [{ tool: "Orders", ok: true, error: "", durationMs: 400 }],
    }]} />);
    expect(html).toContain("Агент запросил «Orders» · 0,4 с");
    expect(html).toContain('role="alert">Unavailable');
  });
});
