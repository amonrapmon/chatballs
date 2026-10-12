import { useImperativeHandle, useLayoutEffect, useRef, type ClipboardEvent, type KeyboardEvent, type Ref, type RefObject } from "react";

import { TEMPLATE_TOKEN } from "../conversations/templateVariables";
import type { TemplateVariable } from "./api";
import { editorText, fillerBreak, hasStaleFiller, selectionOffsets, setEditorCaret } from "./tokenEditorDom";
import "./token-editor.css";

export type TokenEditorHandle = { focus: () => void; insert: (text: string) => void };

// Поле текста с метками переменных (кадры N5, N6, T3): метка показывает
// подпись из каталога, а в значении остаётся исходный маркер. Текст и вставки
// никогда не разбираются как HTML — узлы собираются из строк.

export function TokenEditor({ value, onChange, variables, invalidKeys = [], chipKeys, label, placeholder, className = "", editorRef, fieldRef, onKeyDown, onPaste, disabled = false }: {
  value: string;
  onChange: (value: string) => void;
  variables: TemplateVariable[];
  /** Ключи с ошибкой: неизвестная переменная в шаблоне, незаполненная в ответе. */
  invalidKeys?: string[];
  /** Если задан, меткой становятся только эти ключи; остальное — обычный текст. */
  chipKeys?: string[];
  label: string;
  placeholder?: string;
  className?: string;
  editorRef?: Ref<TokenEditorHandle>;
  /** Сам узел поля — тому, кто выравнивает по нему соседние слои. */
  fieldRef?: RefObject<HTMLDivElement | null>;
  onKeyDown?: (event: KeyboardEvent<HTMLDivElement>) => void;
  onPaste?: (event: ClipboardEvent<HTMLDivElement>) => void;
  disabled?: boolean;
}) {
  const nodeRef = useRef<HTMLDivElement>(null);
  const selectionRef = useRef<{ start: number; end: number } | null>(null);
  const pendingCaret = useRef<number | null>(null);
  const drawnKey = useRef("");
  const chipsKey = `${invalidKeys.join("|")}#${chipKeys?.join("|") ?? "*"}#${variables.length}`;

  function rememberSelection() {
    if (nodeRef.current) selectionRef.current = selectionOffsets(nodeRef.current) ?? selectionRef.current;
  }

  function draw(text: string) {
    const node = nodeRef.current;
    if (!node) return;
    const fragment = document.createDocumentFragment();
    let offset = 0;
    for (const match of text.matchAll(TEMPLATE_TOKEN)) {
      const key = match[1].trim();
      if (chipKeys && !chipKeys.includes(key)) continue;
      if (match.index > offset) fragment.append(document.createTextNode(text.slice(offset, match.index)));
      const chip = document.createElement("span");
      chip.dataset.token = match[0];
      chip.contentEditable = "false";
      chip.className = `template-variable-chip ${invalidKeys.includes(key) ? "is-invalid" : ""}`.trim();
      chip.textContent = variables.find((item) => item.key === key)?.label ?? match[0];
      chip.title = match[0];
      fragment.append(chip);
      offset = match.index + match[0].length;
    }
    if (offset < text.length) fragment.append(document.createTextNode(text.slice(offset)));
    if (text.endsWith("\n")) fragment.append(fillerBreak());
    node.replaceChildren(fragment);
  }

  // Именно layout-эффект: отложенный эффект мог сработать уже после следующего
  // нажатия клавиши и перерисовать поле прежним текстом, сдвинув курсор.
  useLayoutEffect(() => {
    const node = nodeRef.current;
    if (!node) return;
    const focused = document.activeElement === node;
    const caret = pendingCaret.current ?? (focused ? selectionOffsets(node)?.start ?? null : null);
    if (editorText(node) !== value || pendingCaret.current !== null || drawnKey.current !== chipsKey) {
      draw(value);
      if (focused && caret !== null) setEditorCaret(node, caret);
    }
    drawnKey.current = chipsKey;
    pendingCaret.current = null;
  }, [value, chipsKey]);

  function insert(text: string) {
    const node = nodeRef.current;
    if (!node) return;
    const current = editorText(node);
    // Меню переменных и эмодзи забирают фокус: тогда действует позиция,
    // запомненная до его потери, а не сброшенное браузером выделение.
    const live = document.activeElement === node ? selectionOffsets(node) : null;
    const selected = live ?? selectionRef.current ?? { start: current.length, end: current.length };
    pendingCaret.current = selected.start + text.length;
    selectionRef.current = { start: pendingCaret.current, end: pendingCaret.current };
    node.focus();
    onChange(current.slice(0, selected.start) + text + current.slice(selected.end));
  }

  function handleInput() {
    const node = nodeRef.current;
    if (!node) return;
    // Стёртое целиком поле браузер оставляет с одними `<br>`: это пустой текст,
    // а без очистки узлов не вернётся подсказка.
    const emptied = node.textContent === "" && !node.querySelector("[data-token]");
    const text = emptied ? "" : editorText(node);
    if (emptied) node.replaceChildren();
    else if (hasStaleFiller(node)) pendingCaret.current = selectionOffsets(node)?.start ?? text.length;
    rememberSelection();
    onChange(text);
  }

  useImperativeHandle(editorRef, () => ({ focus: () => nodeRef.current?.focus(), insert }));

  return (
    <div
      ref={(node) => {
        nodeRef.current = node;
        if (fieldRef) fieldRef.current = node;
      }}
      role="textbox"
      aria-label={label}
      aria-multiline="true"
      aria-invalid={invalidKeys.length > 0}
      aria-disabled={disabled}
      contentEditable={!disabled}
      suppressContentEditableWarning
      data-placeholder={placeholder}
      className={`template-token-editor ${className}`.trim()}
      onInput={handleInput}
      onKeyUp={rememberSelection}
      onMouseUp={rememberSelection}
      onBlur={() => {
        rememberSelection();
        // Набранный вручную маркер становится меткой, когда поле теряет фокус.
        if (nodeRef.current) draw(editorText(nodeRef.current));
      }}
      onKeyDown={(event) => {
        onKeyDown?.(event);
        // Перенос строки вставляем сами: браузеры размечают его по-разному.
        if (!event.defaultPrevented && event.key === "Enter" && !event.nativeEvent.isComposing) {
          event.preventDefault();
          insert("\n");
        }
      }}
      onPaste={(event) => {
        onPaste?.(event);
        if (event.defaultPrevented) return;
        event.preventDefault();
        insert(event.clipboardData.getData("text/plain").replace(/\r\n?/g, "\n"));
      }}
    />
  );
}
