import { useEffect } from "react";

import { markConversationRead } from "./model";

/** Открытый диалог гасит свои уведомления.
 *
 * Раньше оклик «клиент ждёт» оставался непрочитанным, даже когда сотрудник уже
 * отвечал в этой переписке: прочтением считалось только нажатие на строку в
 * шторке. Счётчик в шапке жил своей жизнью и переставал что-либо значить.
 *
 * Список уведомлений после этого перезапрашивает шапка — по событию, которое
 * шлёт сервер тому же сотруднику: вкладок у него может быть несколько.
 */
export function useOpenedConversationRead(conversationId: number | null): void {
  useEffect(() => {
    if (conversationId == null) return;
    void markConversationRead(conversationId).catch(() => undefined);
  }, [conversationId]);
}
