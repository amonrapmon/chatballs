import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { t } from "../../i18n";
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
  errorText?: string;
};

export function useEmployeeDirectory(): EmployeeDirectory {
  const [employees, setEmployees] = useState<ChatDirectoryEmployee[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState("");
  const settledQuery = useDebounced(query.trim());
  const [revision, setRevision] = useState(0);
  useAvailabilityRefresh(() => setRevision((value) => value + 1));

  useEffect(() => {
    let active = true;
    setLoading(true);
    setErrorText("");
    fetchChatDirectory(settledQuery)
      .then((payload) => {
        if (!active) return;
        setEmployees(payload.employees ?? []);
        setHasMore(Boolean(payload.hasMoreEmployees));
      })
      .catch((problem) => {
        if (active) { setEmployees([]); setErrorText(problem instanceof ApiError ? problem.message : t("common.request_failed")); }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [settledQuery, revision]);

  return { employees, query, setQuery, hasMore, loading, errorText };
}
