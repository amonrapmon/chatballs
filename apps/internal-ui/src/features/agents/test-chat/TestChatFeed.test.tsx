import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";
import { setPreLoginLanguage } from "../../../i18n";
import { TestChatFeed } from "./TestChatFeed";

describe("test chat tool calls", () => {
  beforeEach(() => setPreLoginLanguage("ru"));
  it("shows the server snapshot in the existing reply shell without internal operation chips", () => {
    const html = renderToStaticMarkup(<TestChatFeed agentName="Support" turns={[{
      message: "Order", reply: "Saved text", createdAt: "2026-10-05T17:02:00", calls: [],
      presentation: { formatVersion: 1, isolation: "sandboxed-iframe", sandbox: "", css: "",
        srcDoc: '<!doctype html><html><head></head><body><p>Saved card</p></body></html>' },
    }]} />);
    expect(html).toContain("agent-test-reply");
    expect(html).toContain('sandbox=""');
    expect(html).toContain("Saved card");
    expect(html).not.toContain("tool-call-chip");
  });
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
