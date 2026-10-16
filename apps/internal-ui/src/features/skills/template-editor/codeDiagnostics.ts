import { jsonLanguage } from "@codemirror/lang-json";
import type { Diagnostic } from "./api";

/** Locate a typed data path in JSON syntax, including repeated keys in lists.
 * Missing keys point to their containing object. No evaluation of user code.
 */
export function diagnosticLine(source: string, error: Diagnostic): number {
  if (error.line) return error.line;
  if (error.tab !== "example" || !error.path) return 1;
  const parts = error.path.replace(/\[(\d+)\]/g, ".$1").split(".");
  let node = jsonLanguage.parser.parse(source).topNode.firstChild;
  for (const part of parts) {
    if (!node) break;
    if (node.name === "Object") {
      const property = node.getChildren("Property").find((item) => {
        const key = item.getChild("PropertyName");
        try { return key && JSON.parse(source.slice(key.from, key.to)) === part; }
        catch { return false; }
      });
      if (!property) break;
      node = property.lastChild;
    } else if (node.name === "Array") {
      const values = [];
      for (let child = node.firstChild; child; child = child.nextSibling) {
        if (!["[", "]", ","].includes(child.name)) values.push(child);
      }
      node = values[Number(part)] ?? node;
    } else break;
  }
  return source.slice(0, node?.from ?? 0).split("\n").length;
}
