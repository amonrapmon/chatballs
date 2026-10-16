import { useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import { useAvailabilityRefresh } from "../work-status/useAvailabilityRefresh";
import { fetchChatDirectory, type ApiConversation, type ChatDirectoryEmployee } from "./model";

// Выбранный ответственный не обязан входить в поисковую выдачу меню.
// Читаем его штатным поиском и обязательно сверяем id; прежнее значение
// сохраняется при временном обрыве, но не после отказа в доступе.
export function useAssigneeAvailability(assignee: ApiConversation["assignedOperator"], employees: ChatDirectoryEmployee[]) {
  const [selected, setSelected] = useState<ChatDirectoryEmployee | undefined>();
  const [revision, setRevision] = useState(0);
  useAvailabilityRefresh(() => setRevision((value) => value + 1));
  const listed = employees.find((employee) => employee.id === assignee?.id);

  useEffect(() => {
    let active = true;
    if (listed || !assignee) {
      setSelected(listed);
      return;
    }
    void fetchChatDirectory(assignee.name).then((payload) => {
      if (active) setSelected(payload.employees.find((employee) => employee.id === assignee.id));
    }).catch((error) => {
      if (active && error instanceof ApiError && [403, 404].includes(error.status)) setSelected(undefined);
    });
    return () => { active = false; };
  }, [assignee?.id, assignee?.name, listed, revision]);

  return listed ?? (selected?.id === assignee?.id ? selected : undefined);
}
