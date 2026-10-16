import type { MessagePresentation } from "@chatballs/contracts";

// Defence in depth for damaged/unsupported persisted envelopes. The server is
// still responsible for compilation and sanitization; never render contentHtml.
const CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'";
const INTERNAL = /<<HANDOFF>>|CHATBALLS_PREPARED:[^\s<]*|\[\[[^\]]*\]\]/g;

export function snapshotText(text: string): string {
  return text.replace(INTERNAL, "");
}

export function snapshotDocument(content: MessagePresentation, mode?: "html" | "text"): string | null {
  const view = content.presentation;
  if ((mode ?? content.deliveryRepresentation ?? "html") !== "html"
    || (content.formatVersion !== undefined && content.formatVersion !== 1)
    || view?.formatVersion !== 1 || view.isolation !== "sandboxed-iframe" || view.sandbox !== ""
    || typeof view.srcDoc !== "string" || !view.srcDoc.trim()) return null;
  const doc = view.srcDoc;
  const meta = doc.match(/<meta\b[^>]*>/gi) ?? [];
  if (!/^<!doctype html><html><head>/i.test(doc) || !/<\/body><\/html>$/i.test(doc)
    || meta.some((tag) => !/^<meta (charset="utf-8"|http-equiv="Content-Security-Policy" content="[^"<>]*"|name="referrer" content="no-referrer")>$/i.test(tag))
    || /<(script|iframe|object|embed|base|link|img|foreignObject|animate|form|video|audio|source)\b/i.test(doc)
    || /\bon\w+\s*=|http-equiv\s*=\s*["']?refresh|<<HANDOFF>>|CHATBALLS_PREPARED:|\[\[/i.test(doc)) return null;
  // First policy applies before any persisted markup, even if its CSP is lost.
  return doc.replace(/<head>/i, `<head><meta http-equiv="Content-Security-Policy" content="${CSP}">`);
}
