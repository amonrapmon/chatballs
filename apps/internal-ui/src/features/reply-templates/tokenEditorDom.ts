// DOM-часть редактора с метками переменных: текст поля ↔ узлы, позиция
// курсора в символах исходного текста. Метка хранит свой маркер в data-token.

/** Перенос в конце текста браузер не показывает новой строкой без `<br>`
 *  следом; такой `<br>` служебный и в текст не попадает. */
const FILLER = "filler";

export function editorText(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
  if (node instanceof HTMLElement) {
    if (node.dataset.token) return node.dataset.token;
    if (node.tagName === "BR") return node.dataset[FILLER] ? "" : "\n";
  }
  return Array.from(node.childNodes).map((child, index) => {
    const text = editorText(child);
    return child instanceof HTMLElement && ["DIV", "P"].includes(child.tagName) && index > 0 ? `\n${text}` : text;
  }).join("");
}

export function fillerBreak(): HTMLBRElement {
  const node = document.createElement("br");
  node.dataset[FILLER] = "1";
  return node;
}

/** Служебный перенос оказался не последним узлом: браузер дописал текст после
 *  него, и поле нужно перерисовать, иначе на экране лишняя пустая строка. */
export function hasStaleFiller(editor: HTMLElement): boolean {
  const filler = editor.querySelector(`br[data-${FILLER}]`);
  return filler !== null && filler !== editor.lastChild;
}

export function selectionOffsets(editor: HTMLElement): { start: number; end: number } | null {
  const selection = window.getSelection();
  if (!selection?.rangeCount || !editor.contains(selection.anchorNode)) return null;
  const selected = selection.getRangeAt(0);
  const prefix = selected.cloneRange();
  prefix.selectNodeContents(editor);
  prefix.setEnd(selected.startContainer, selected.startOffset);
  const start = editorText(prefix.cloneContents()).length;
  return { start, end: start + editorText(selected.cloneContents()).length };
}

export function setEditorCaret(editor: HTMLElement, offset: number) {
  const range = document.createRange();
  let remaining = offset;
  let placed = false;
  for (const child of Array.from(editor.childNodes)) {
    const size = editorText(child).length;
    if (remaining <= size) {
      if (child.nodeType === Node.TEXT_NODE) range.setStart(child, remaining);
      else if (remaining === 0) range.setStartBefore(child);
      else range.setStartAfter(child);
      placed = true;
      break;
    }
    remaining -= size;
  }
  if (!placed) range.selectNodeContents(editor);
  range.collapse(placed);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
}
