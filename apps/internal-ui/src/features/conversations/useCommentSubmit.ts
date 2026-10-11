import { useCallback, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { t } from "../../i18n";
import { createComment } from "./commentApi";

// Ключ операции — UUID. randomUUID доступен только в защищённом контексте,
// getRandomValues — везде, где открывается рабочее место.
function newOperationId(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** Причина отказа словами сервера: общая или по полю запроса. */
function serverReason(error: ApiError): string {
  if (error.payload.detail) return error.payload.detail;
  for (const value of Object.values(error.payload)) {
    const first: unknown = Array.isArray(value) ? value[0] : value;
    if (typeof first === "string" && first) return first;
  }
  return error.message;
}

/** Отправка внутреннего комментария (кадры C2–C3). Идёт только маршрутом
 *  комментариев: в переписку с клиентом отсюда ничего не попадает. */
export function useCommentSubmit(conversationId: number | null, onSaved: () => void) {
  const [sending, setSending] = useState(false);
  const [errorText, setErrorText] = useState("");
  // «Повторить» отправляет тот же текст с прежним ключом: если первая попытка
  // дошла до сервера, а ответ потерялся, второй комментарий не появится.
  const attemptRef = useRef<{ text: string; operationId: string } | null>(null);

  const submit = useCallback(async (text: string): Promise<boolean> => {
    if (conversationId == null) return false;
    const attempt = attemptRef.current?.text === text ? attemptRef.current : { text, operationId: newOperationId() };
    attemptRef.current = attempt;
    setSending(true);
    setErrorText("");
    try {
      await createComment(conversationId, text, attempt.operationId);
      attemptRef.current = null;
      onSaved();
      return true;
    } catch (error) {
      setErrorText(error instanceof ApiError ? serverReason(error) : t("comments.not_saved_offline"));
      return false;
    } finally {
      setSending(false);
    }
  }, [conversationId, onSaved]);

  return { sending, errorText, submit };
}
