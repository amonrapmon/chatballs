import { useCallback, useState } from "react";

// Сколько записей показывать на странице. Выбор принадлежит человеку и его
// браузеру: у одного список на ноутбуке, у другого — на широком мониторе, и
// навязывать обоим одно число незачем. Верхняя граница — потолок сервера
// (`api/pagination.py`, MAX_PAGE_SIZE).

export const PAGE_SIZE_OPTIONS = [20, 50, 100];
export const DEFAULT_PAGE_SIZE = 20;

const STORAGE_PREFIX = "chatballs.ui.pageSize.";

function readStored(key: string, fallback: number): number {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + key);
    const value = raw ? Number(raw) : NaN;
    return PAGE_SIZE_OPTIONS.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

export function usePageSize(key: string, fallback = DEFAULT_PAGE_SIZE) {
  const [pageSize, setStored] = useState(() => readStored(key, fallback));

  const setPageSize = useCallback((next: number) => {
    setStored(next);
    try {
      window.localStorage.setItem(STORAGE_PREFIX + key, String(next));
    } catch {
      /* без сохранения — выбор держится до перезагрузки */
    }
  }, [key]);

  return { pageSize, setPageSize };
}
