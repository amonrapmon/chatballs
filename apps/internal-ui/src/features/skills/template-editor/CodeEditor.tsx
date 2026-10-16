import { useEffect, useRef } from "react";
import { Compartment, EditorState } from "@codemirror/state";
import { Decoration, EditorView, WidgetType, keymap, lineNumbers, drawSelection, MatchDecorator, ViewPlugin } from "@codemirror/view";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags } from "@lezer/highlight";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { json } from "@codemirror/lang-json";
import { diagnosticLine } from "./codeDiagnostics";
import type { Diagnostic } from "./api";

class ErrorWidget extends WidgetType {
  constructor(readonly message: string) { super(); }
  eq(other: ErrorWidget) { return this.message === other.message; }
  toDOM() { const element = document.createElement("div"); element.className = "template-code-error"; element.textContent = this.message; return element; }
}
const highlighting = HighlightStyle.define([
  { tag: [tags.tagName, tags.angleBracket, tags.propertyName], color: "var(--primary-text)" },
  { tag: [tags.attributeName, tags.attributeValue], color: "var(--ai)" },
  { tag: tags.string, color: "var(--success-text)" },
  { tag: [tags.number, tags.bool, tags.null], color: "var(--warning-text)" },
]);
const matcher = new MatchDecorator({ regexp: /\{\{[^}]*\}\}/g, decoration: Decoration.mark({ class: "template-token" }) });
const templateTokens = ViewPlugin.fromClass(class {
  decorations;
  constructor(view: EditorView) { this.decorations = matcher.createDeco(view); }
  update(update: Parameters<typeof matcher.updateDeco>[0]) { this.decorations = matcher.updateDeco(update, this.decorations); }
}, { decorations: (plugin) => plugin.decorations });
const theme = EditorView.theme({
  "&": { height: "100%", fontSize: "12px", background: "var(--n-10)", color: "var(--n-2)" },
  ".cm-scroller": { overflow: "auto", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", lineHeight: "20px" },
  ".cm-content": { padding: "10px 0", caretColor: "var(--n-1)" },
  ".cm-gutters": { background: "var(--n-10)", color: "var(--n-5)", border: "none", minWidth: "40px" },
  ".cm-lineNumbers .cm-gutterElement": { paddingRight: "12px" },
  ".cm-line": { padding: "0 10px 0 0" },
  ".template-token, .template-token span": { color: "#0f9b8e !important", fontWeight: "600" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": { background: "var(--primary-bg)" },
  ".template-code-invalid": { background: "var(--error-bg)", boxShadow: "inset 3px 0 var(--error-text)" },
  ".template-code-error": { color: "var(--error-text)", background: "var(--error-bg)", padding: "3px 10px", font: "11.5px/1.4 system-ui,sans-serif" },
});

export function CodeEditor({ value, change, language, errors, label, disabled = false }: {
  value: string; change: (value: string) => void; language: "html" | "css" | "text" | "example";
  errors: Diagnostic[]; label: string; disabled?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const callback = useRef(change);
  const compartments = useRef({ language: new Compartment(), diagnostics: new Compartment(), editable: new Compartment() });
  callback.current = change;
  useEffect(() => {
    const instance = new EditorView({ parent: host.current!, state: EditorState.create({ doc: value, extensions: [
      lineNumbers(), drawSelection(), history(), theme, syntaxHighlighting(highlighting), templateTokens,
      compartments.current.language.of([]), compartments.current.diagnostics.of([]), compartments.current.editable.of([]),
      keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
      EditorView.updateListener.of((update) => { if (update.docChanged) callback.current(update.state.doc.toString()); }),
      EditorView.contentAttributes.of({ "aria-label": label, "aria-multiline": "true", role: "textbox" }),
    ] }) });
    view.current = instance;
    return () => { instance.destroy(); view.current = null; };
  }, []);
  useEffect(() => {
    const instance = view.current!;
    if (instance.state.doc.toString() !== value) instance.dispatch({ changes: { from: 0, to: instance.state.doc.length, insert: value } });
    const extensions = language === "html" ? html() : language === "css" ? css() : language === "example" ? json() : [];
    instance.dispatch({ effects: [compartments.current.language.reconfigure(extensions),
      compartments.current.editable.reconfigure(EditorView.editable.of(!disabled))] });
  }, [value, language, disabled]);
  useEffect(() => {
    const instance = view.current!;
    const marks = errors.flatMap((error) => {
      const number = Math.min(instance.state.doc.lines, Math.max(1, diagnosticLine(value, error)));
      const line = instance.state.doc.line(number);
      return [Decoration.line({ class: "template-code-invalid" }).range(line.from),
        Decoration.widget({ widget: new ErrorWidget((error.reference ? `${error.reference}: ` : "") + error.detail), block: true, side: 1 }).range(line.to)];
    });
    instance.dispatch({ effects: compartments.current.diagnostics.reconfigure(EditorView.decorations.of(Decoration.set(marks, true))) });
  }, [value, errors]);
  return <div className="template-code-editor" ref={host} />;
}
