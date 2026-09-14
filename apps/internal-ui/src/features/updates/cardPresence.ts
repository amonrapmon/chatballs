import { useEffect, useSyncExternalStore } from "react";

// Полоса поверх рабочей области и карточка «Обновления» рассказывают одно и то
// же. Когда карточка на экране, полоса молчит: два сообщения об одном событии
// рядом — это не «заметнее», а шум, и человек перестаёт читать оба.

let mounted = 0;
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Карточка на экране, пока смонтирована. */
export function useUpdatesCardPresence(): void {
  useEffect(() => {
    mounted += 1;
    listeners.forEach((listener) => listener());
    return () => {
      mounted -= 1;
      listeners.forEach((listener) => listener());
    };
  }, []);
}

export function useUpdatesCardVisible(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => mounted > 0,
    () => false,
  );
}
