import { useEffect, useState } from "react";
import { useAvailabilityRefresh } from "../work-status/useAvailabilityRefresh";

import { useDebounced } from "../../shared/useDebounced";
import { fetchChatDirectory, type ChatDirectoryEmployee } from "./model";

// Справочник коллег для выбора ответственного (кадр G). Сервер отдаёт
// ограниченную выдачу и ищет сам: в организации может быть сколько угодно
// сотрудников, а выбор — не список.

export type EmployeeDirectory = {
  employees: ChatDirectoryEmployee[];
  query: string;
  setQuery: (query: string) => void;
  /** За пределами выдачи есть ещё коллеги — выбору нужна строка поиска. */
  hasMore: boolean;
  loading: boolean;
};

export function useEmployeeDirectory(): EmployeeDirectory {
  const [employees, setEmployees] = useState<ChatDirectoryEmployee[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const settledQuery = useDebounced(query.trim());
  const [revision, setRevision] = useState(0);
  useAvailabilityRefresh(() => setRevision((value) => value + 1));

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchChatDirectory(settledQuery)
      .then((payload) => {
        if (!active) return;
        setEmployees(payload.employees ?? []);
        setHasMore(Boolean(payload.hasMoreEmployees));
      })
      .catch(() => {
        if (active) setEmployees([]);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [settledQuery, revision]);

  return { employees, query, setQuery, hasMore, loading };
}
