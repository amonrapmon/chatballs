import { useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";

// Плавающий элемент, который человек перетаскивает мышью: положение считается
// от правого нижнего угла окна и живёт в localStorage этого браузера.
//
// Отступ от края — от правого и нижнего, а не от левого и верхнего: элемент
// прижат к этому углу и при изменении размера окна должен оставаться там же,
// а не уезжать за границу вместе с координатой.

export type EdgeOffset = { right: number; bottom: number };

const STORAGE_PREFIX = "chatballs.ui.position.";
// Ближе к краю элемент не подводим: кнопка, прижатая вплотную, читается как
// обрезанная, а на краю окна её ещё и трудно поймать курсором.
const EDGE_GAP = 8;
// Сдвиг меньше этого — не перетаскивание, а дрожание руки при клике.
const DRAG_THRESHOLD = 3;

function clamp(value: number, max: number): number {
  return Math.min(Math.max(value, EDGE_GAP), Math.max(EDGE_GAP, max));
}

function readStored(key: string, fallback: EdgeOffset): EdgeOffset {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + key);
    if (!raw) return fallback;
    const stored = JSON.parse(raw) as Partial<EdgeOffset>;
    return Number.isFinite(stored.right) && Number.isFinite(stored.bottom)
      ? { right: Number(stored.right), bottom: Number(stored.bottom) }
      : fallback;
  } catch {
    return fallback;
  }
}

export function useDraggablePosition<T extends HTMLElement>(key: string, fallback: EdgeOffset) {
  const [offset, setOffset] = useState<EdgeOffset>(() => readStored(key, fallback));
  const [dragging, setDragging] = useState(false);
  const ref = useRef<T | null>(null);
  // Клик по элементу приходит и после перетаскивания: без этой отметки
  // отпущенная кнопка тут же срабатывала бы как нажатая.
  const moved = useRef(false);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(offset));
    } catch {
      /* без сохранения — положение держится до перезагрузки */
    }
  }, [key, offset]);

  const fit = useCallback((next: EdgeOffset): EdgeOffset => {
    const box = ref.current?.getBoundingClientRect();
    const width = box?.width ?? 0;
    const height = box?.height ?? 0;
    return {
      right: clamp(next.right, window.innerWidth - width - EDGE_GAP),
      bottom: clamp(next.bottom, window.innerHeight - height - EDGE_GAP),
    };
  }, []);

  // Окно уменьшили — элемент возвращается в видимую область, иначе он остался
  // бы за краем и человек больше не смог бы до него дотянуться.
  useEffect(() => {
    const onResize = () => setOffset((current) => fit(current));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [fit]);

  const onPointerDown = useCallback((event: ReactPointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    const start = { x: event.clientX, y: event.clientY, ...offset };
    moved.current = false;
    setDragging(true);
    const move = (moveEvent: PointerEvent) => {
      const shiftX = start.x - moveEvent.clientX;
      const shiftY = start.y - moveEvent.clientY;
      if (Math.abs(shiftX) > DRAG_THRESHOLD || Math.abs(shiftY) > DRAG_THRESHOLD) moved.current = true;
      setOffset(fit({ right: start.right + shiftX, bottom: start.bottom + shiftY }));
    };
    const up = () => {
      setDragging(false);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      document.body.style.userSelect = "";
    };
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }, [fit, offset]);

  const style: CSSProperties = { right: offset.right, bottom: offset.bottom };
  return { dragging, onPointerDown, ref, style, wasDragged: () => moved.current };
}
