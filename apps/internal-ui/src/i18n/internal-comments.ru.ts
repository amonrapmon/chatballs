import type { Message } from "@chatballs/shared";

// Внутренние комментарии в переписке: выбор аудитории в редакторе и запись в ленте.
export const internalCommentsRu = {
  "comments.add": "Добавить комментарий",
  "comments.audience_client": "Увидит клиент · {channel}",
  "comments.audience_staff": "Только сотрудники — клиент не увидит",
  "comments.feed_actor": "{name} · внутренний комментарий",
  "comments.field_placeholder": "Комментарий для коллег… Клиент его не увидит",
  "comments.not_saved_offline": "Комментарий не сохранён: нет связи с сервером.",
  "comments.switched_to_reply": "Вы переключились на ответ клиенту — этот текст увидит {name}.",
  "comments.tab_comment": "Комментарий",
  "comments.tab_comment_hint": "Внутренний комментарий — только для сотрудников",
  "comments.tab_comment_short": "Коммент.",
  "comments.tab_reply": "Ответ клиенту",
  "comments.tab_reply_short": "Клиенту",
} as const satisfies Record<string, Message>;
