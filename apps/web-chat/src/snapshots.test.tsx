import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Bubble } from "./ChatMessages";

describe("widget saved snapshots", () => {
  const snapshot = { formatVersion: 1 as const, presentation: {
    formatVersion: 1 as const, isolation: "sandboxed-iframe" as const, sandbox: "" as const, css: "",
    srcDoc: '<!doctype html><html><head></head><body><p>Saved card</p></body></html>',
  } };
  it("uses the shared isolated renderer only for outgoing AI snapshots", () => {
    const render = (author: "ai" | "client", view = snapshot) => renderToStaticMarkup(
      <Bubble author={author} authorName="Support" accent="#1677ff" text="Saved text" snapshot={view} />);
    expect(render("ai")).toContain('sandbox=""');
    expect(render("ai")).not.toContain("allow-scripts");
    expect(render("client")).not.toContain("iframe");
    expect(render("client")).toContain("Saved text");
  });
  it("shows the sent text for text delivery and preserves ordinary replies", () => {
    for (const view of [undefined, { ...snapshot, deliveryRepresentation: "text" as const }]) {
      const html = renderToStaticMarkup(<Bubble author="ai" authorName="Support" accent="#1677ff" text="Saved text" snapshot={view} />);
      expect(html).toContain("Saved text");
      expect(html).not.toContain("iframe");
    }
  });
});
