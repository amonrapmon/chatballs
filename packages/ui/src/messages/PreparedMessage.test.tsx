import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PreparedMessage, type PreparedContent } from "./PreparedMessage";

describe("prepared snapshot rendering boundary", () => {
  it("isolates server HTML/CSS from the host and denies execution in both documents", () => {
    const content: PreparedContent = { text: "Plain", presentation: { formatVersion: 1,
      isolation: "sandboxed-iframe", sandbox: "", css: "", srcDoc: '<!doctype html><html><head></head><body><p id="untrusted">Card</p></body></html>' } };
    const markup = renderToStaticMarkup(<PreparedMessage content={content} title="Preview" />);
    expect(markup).toContain('sandbox=""');
    expect(markup).not.toContain("allow-scripts");
    expect(markup).not.toContain('<p id="untrusted">');
    expect(markup).toContain("&lt;p id=&quot;untrusted&quot;&gt;");
  });
  it("uses the saved escaped text for text delivery and unsupported formats", () => {
    const content = { text: '<script>alert(1)</script>\nSaved text', contentHtml: "Ignored" };
    const markup = renderToStaticMarkup(<PreparedMessage content={content} title="Text" mode="text" />);
    expect(markup).not.toContain("iframe");
    expect(markup).toContain("&lt;script&gt;");
    expect(markup).toContain("Saved text");
    expect(markup).not.toContain("Ignored");
  });
  it("respects the saved delivery representation when the caller does not override it", () => {
    const content: PreparedContent = { text: "Saved transport text", deliveryRepresentation: "text",
      presentation: { formatVersion: 1, isolation: "sandboxed-iframe", sandbox: "", css: "", srcDoc: "<p>Card</p>" } };
    const markup = renderToStaticMarkup(<PreparedMessage content={content} title="Message" />);
    expect(markup).not.toContain("iframe");
    expect(markup).toContain("Saved transport text");
  });
  it.each([null, {}, { formatVersion: 2 }, { formatVersion: 1, isolation: "sandboxed-iframe", sandbox: "", srcDoc: "" },
    { formatVersion: 1, isolation: "sandboxed-iframe", sandbox: "", srcDoc: '<!doctype html><html><head><meta http-equiv="refresh" content="0;url=https://example.com"></head><body></body></html>' },
  ])("falls back without exposing internal references for a damaged envelope %j", (presentation) => {
    const content = { text: "Saved text [[private_token]] CHATBALLS_PREPARED:secret <<HANDOFF>>", presentation } as PreparedContent;
    const markup = renderToStaticMarkup(<PreparedMessage content={content} title="Message" />);
    expect(markup).toContain("Saved text");
    expect(markup).not.toMatch(/iframe|private_token|CHATBALLS_PREPARED|HANDOFF/);
  });
});
