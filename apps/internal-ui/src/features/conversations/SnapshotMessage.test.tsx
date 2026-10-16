import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";
import { setPreLoginLanguage } from "../../i18n";
import { SnapshotMessage } from "./SnapshotMessage";
import type { ApiMessage } from "./apiTypes";

describe("employee saved snapshots", () => {
  beforeEach(() => setPreLoginLanguage("ru"));
  const message: ApiMessage = { id: 1, author: "AI", text: "Sent text", createdAt: "2026-10-16T12:00:00Z",
    formatVersion: 1, deliveryRepresentation: "html",
    template: { skillId: "s", skillRevision: 1, id: "t", name: "Sent template name" },
    presentation: { formatVersion: 1, isolation: "sandboxed-iframe", sandbox: "", css: "",
      srcDoc: '<!doctype html><html><head></head><body><p>Saved card</p></body></html>' } };
  const render = (item: ApiMessage) => renderToStaticMarkup(<SnapshotMessage message={item}
    bubble={{ side: "ai", actor: "AI · Support", time: "15:00" }} />);
  it("keeps actor, time and read mark and labels the snapshot from sent metadata", () => {
    const html = render(message);
    expect(html).toContain("AI · Support");
    expect(html).toContain("15:00");
    expect(html).toContain("Sent template name");
    expect(html).toContain("Текстовая версия");
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain("изменён");
  });
  it("shows a revision hint only when the history contract confirms it", () => {
    const html = render({ ...message, templateUpdatedAt: "2026-10-16T12:00:00Z" });
    expect(html).toContain("изменён");
    expect(html).toContain("Saved card");
  });
  it("shows actually sent text for text delivery without template actions", () => {
    const html = render({ ...message, deliveryRepresentation: "text" });
    expect(html).toContain("Sent text");
    expect(html).not.toContain("iframe");
    expect(html).not.toContain("Текстовая версия");
  });
  it("localizes the snapshot actions and explanation in English", () => {
    setPreLoginLanguage("en");
    const html = render({ ...message, templateUpdatedAt: "2026-10-16T12:00:00Z" });
    expect(html).toContain("Text version");
    expect(html).toContain("This is how the customer received the message.");
  });
});
