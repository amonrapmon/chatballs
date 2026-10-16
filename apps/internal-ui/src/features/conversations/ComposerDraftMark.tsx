import { useEffect, type DependencyList, type RefObject } from "react";

// Метка у текста из черновика (кадр A6) стоит сразу за последним символом.
// Соседа у редактируемого текста быть не может — он попал бы в сам текст,
// поэтому поверх поля лежит невидимая копия текста с той же вёрсткой, а метка
// идёт в ней следом. Метка видна только оператору: в отправляемый текст она не
// попадает.
export function ComposerDraftMark({ text, label, ref }: { text: string; label: string; ref: RefObject<HTMLDivElement | null> }) {
  return (
    <div className="composer-field-mirror" aria-hidden="true" ref={ref}>
      <span>{text}</span>
      <span className="composer-draft-mark">{label}</span>
    </div>
  );
}

/** Держит копию вровень с полем. Поле растёт под текст само, предел задаёт CSS. */
export function useDraftMarkLayout(fieldRef: RefObject<HTMLElement | null>, mirrorRef: RefObject<HTMLDivElement | null>, deps: DependencyList) {
  useEffect(() => {
    const field = fieldRef.current;
    const mirror = mirrorRef.current;
    if (!field) return;
    const ghost = mirror?.firstElementChild;
    const mark = mirror?.lastElementChild;
    if (!mirror || !ghost || !mark) {
      field.classList.remove("has-mark-line");
      return;
    }
    // Полоса прокрутки сужает строку поля — копия должна переноситься так же.
    const alignWidth = () => { mirror.style.right = `${field.offsetWidth - field.clientWidth}px`; };
    alignWidth();
    // Метка не поместилась за текстом и ушла на свою строку: полю нужна эта строка.
    const lines = ghost.getClientRects();
    const lastLine = lines[lines.length - 1];
    const ownLine = Boolean(lastLine) && mark.getBoundingClientRect().top > lastLine.top + lastLine.height / 2;
    if (field.classList.contains("has-mark-line") !== ownLine) {
      field.classList.toggle("has-mark-line", ownLine);
      alignWidth();
    }
    const followScroll = () => { mirror.scrollTop = field.scrollTop; };
    followScroll();
    field.addEventListener("scroll", followScroll);
    return () => field.removeEventListener("scroll", followScroll);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
