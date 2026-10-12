import { useEffect, type DependencyList, type RefObject } from "react";

/** Поле растёт под текст: высота по содержимому, предел задаёт CSS. */
export function fitTextareaHeight(node: HTMLTextAreaElement) {
  node.style.height = "auto";
  node.style.height = node.scrollHeight > 0 ? `${node.scrollHeight}px` : "";
}

// Метка у текста из черновика (кадр A6) стоит сразу за последним символом.
// У текста в textarea соседа быть не может, поэтому поверх поля лежит невидимая
// копия текста с той же вёрсткой, а метка идёт в ней следом. Метка видна только
// оператору: в отправляемый текст она не попадает.
export function ComposerDraftMark({ text, label, ref }: { text: string; label: string; ref: RefObject<HTMLDivElement | null> }) {
  return (
    <div className="composer-field-mirror" aria-hidden="true" ref={ref}>
      <span>{text}</span>
      <span className="composer-draft-mark">{label}</span>
    </div>
  );
}

/** Держит копию вровень с полем. Вызывается после подгонки высоты поля. */
export function useDraftMarkLayout(areaRef: RefObject<HTMLTextAreaElement | null>, mirrorRef: RefObject<HTMLDivElement | null>, deps: DependencyList) {
  useEffect(() => {
    const area = areaRef.current;
    const mirror = mirrorRef.current;
    if (!area) return;
    const ghost = mirror?.firstElementChild;
    const mark = mirror?.lastElementChild;
    if (!mirror || !ghost || !mark) {
      if (area.classList.contains("has-mark-line")) {
        area.classList.remove("has-mark-line");
        fitTextareaHeight(area);
      }
      return;
    }
    // Полоса прокрутки сужает строку поля — копия должна переноситься так же.
    const alignWidth = () => { mirror.style.right = `${area.offsetWidth - area.clientWidth}px`; };
    alignWidth();
    // Метка не поместилась за текстом и ушла на свою строку: полю нужна эта строка.
    const lines = ghost.getClientRects();
    const lastLine = lines[lines.length - 1];
    const ownLine = Boolean(lastLine) && mark.getBoundingClientRect().top > lastLine.top + lastLine.height / 2;
    if (area.classList.contains("has-mark-line") !== ownLine) {
      area.classList.toggle("has-mark-line", ownLine);
      fitTextareaHeight(area);
      alignWidth();
    }
    const followScroll = () => { mirror.scrollTop = area.scrollTop; };
    followScroll();
    area.addEventListener("scroll", followScroll);
    return () => area.removeEventListener("scroll", followScroll);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
