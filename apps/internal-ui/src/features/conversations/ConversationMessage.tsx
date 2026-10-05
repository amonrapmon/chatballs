import type { ReactNode } from "react";
import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { EmailMessageBody } from "./EmailMessageBody";
import { FileMessage } from "./FileMessage";
import { VoiceMessage } from "./VoiceMessage";
import type { ApiMessage } from "./apiTypes";
import type { ConversationListItem } from "./types";

export function ConversationMessage({ message, dialog, viewerId }: { message: ApiMessage; dialog: ConversationListItem; viewerId: number | null }) {
  if (message.author === "SYSTEM") {
    // Системное событие (кадры B, C): передача — предупреждение, взятие и
    // возврат — акцент. Тон выбирается по коду события, а не по словам в
    // тексте: текст приходит на языке читателя и на английском не совпал бы
    // ни с одной русской регуляркой.
    // «Не взял — вернулся в очередь» окрашено предупреждением намеренно (макет
    // Q4): это не факт из истории, а сорванная договорённость.
    const tone = message.systemEvent === "ai_handed_over"
      || message.systemEvent === "ai_unavailable"
      || message.systemEvent === "assignment_expired"
      ? "warning"
      : message.systemEvent === "operator_took"
        || message.systemEvent === "returned_to_ai"
        || message.systemEvent === "returned_to_queue"
        || message.systemEvent === "assigned_to"
        ? "claimed"
        : "";
    return <div className={`sales-event-chip ${tone}`}><Icon name="clock" size={12} />{message.text}<span>·</span>{fmt.time(message.createdAt)}</div>;
  }
  const side = message.author === "CONTACT" ? "client" : message.author === "OPERATOR" ? "operator" : "ai";
  // Подпись исходящего (решение 4a): «AI · Консультант», «Анна Ким», «Елена Кузнецова · вы».
  const actor = message.author === "AI"
    ? `AI · ${dialog.agentName}`
    : message.author === "OPERATOR"
      ? `${message.authorName || t("common.operator")}${viewerId != null && message.authorUserId === viewerId ? t("common.you_suffix") : ""}`
      : undefined;
  return (
    <Message side={side} actor={actor} actorColor={message.author === "AI" ? dialog.agentColor : undefined} time={fmt.time(message.createdAt)} authorInitials={message.authorName ? initialsOf(message.authorName) : ""} authorAvatarUrl={message.authorAvatarUrl ?? null}>
      {message.kind === "voice"
        ? <VoiceMessage message={message} />
        : message.kind === "file"
          ? <FileMessage message={message} />
        : message.author === "CONTACT" && dialog.channel === "EMAIL"
          ? <EmailMessageBody html={message.contentHtml} text={message.text} />
          : message.text}
    </Message>
  );
}

// Сообщения (решение 4a): у клиента аватара нет — он в шапке; исходящие справа
// с аватаром AI/сотрудника, подписью и отметкой доставки.
function Message({ side, actor, actorColor, authorInitials, authorAvatarUrl, time, children }: { side: "ai" | "client" | "operator"; actor?: string; actorColor?: string; authorInitials?: string; authorAvatarUrl?: string | null; time: string; children: ReactNode }) {
  return (
    <div className={`sales-message ${side}`}>
      {side !== "client" && (
        <div className="sales-message-avatar" style={side === "ai" && actorColor ? { color: actorColor, background: `color-mix(in srgb, ${actorColor} 14%, var(--surface-card))`, borderColor: `color-mix(in srgb, ${actorColor} 30%, var(--surface-card))` } : undefined}>
          {side === "ai" ? <Icon name="robot" size={16} /> : authorAvatarUrl ? <img src={authorAvatarUrl} alt="" /> : <span>{authorInitials}</span>}
        </div>
      )}
      <div className="sales-message-content">
        {actor && <strong style={actorColor ? { color: actorColor } : undefined}>{actor}</strong>}
        <div>{children}</div>
        <small>{time}{side !== "client" && <Icon name="check" size={13} />}</small>
      </div>
    </div>
  );
}

function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase();
}
