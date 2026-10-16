import { describe, expect, it } from "vitest";
import { snapshotDocument } from "./snapshot";

describe("snapshot document defence", () => {
  const document = (body: string) => `<!doctype html><html><head></head><body>${body}</body></html>`;
  const content = (srcDoc: string) => ({ presentation: {
    formatVersion: 1 as const, isolation: "sandboxed-iframe" as const, sandbox: "" as const, css: "", srcDoc,
  } });
  it("adds a resource-denying CSP before persisted styles", () => {
    const result = snapshotDocument(content(document('<style>body{background:url(https://example.com/a)}</style><p>Saved</p>')));
    expect(result?.indexOf("default-src 'none'")).toBeLessThan(result!.indexOf("<style>"));
  });
  it.each(['<script>alert(1)</script>', '<img src="https://example.com">', '<p onclick="evil()">x</p>',
    '<iframe src="https://example.com"></iframe>', '<p>[[unrestored]]</p>'])("rejects active or unresolved content %s", (body) => {
    expect(snapshotDocument(content(document(body)))).toBeNull();
  });
});
