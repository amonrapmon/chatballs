import { Icon } from "../../shared/icons";
import { t } from "../../i18n";
import type { ApiMessage } from "./apiTypes";

type PendingMedia = Pick<ApiMessage, "mediaStatus" | "mediaKind" | "mediaReason" | "mediaRetryable" | "text">;

const reasonKey = {
  PROVIDER_QUOTA: "conversations.media_provider_quota",
  PROVIDER_UNAVAILABLE: "conversations.media_provider_unavailable",
  EXPIRED: "conversations.media_expired",
  UNSUPPORTED_KIND: "conversations.media_unsupported",
  INVALID_MEDIA: "conversations.media_invalid",
  UNKNOWN: "conversations.media_unknown",
} as const;

export function mediaLabel(kind: ApiMessage["mediaKind"]) {
  if (kind === "image") return t("conversations.media_photo");
  if (kind === "voice") return t("conversations.media_voice");
  return t("conversations.media_document");
}

/** A real inbound Message exists, but authenticated native file bytes do not. */
export function MediaLifecycleCard({ message }: { message: PendingMedia }) {
  const failed = message.mediaStatus === "FAILED";
  const icon = message.mediaKind === "voice" ? "mic" : message.mediaKind === "image" ? "image" : "paperclip";
  const reason = message.mediaReason && message.mediaReason in reasonKey
    ? reasonKey[message.mediaReason as keyof typeof reasonKey]
    : "conversations.media_unknown";
  return (
    <div className={`media-lifecycle-card ${failed ? "is-failed" : "is-pending"}`} role="status" aria-live="polite">
      <span className="media-lifecycle-icon"><Icon name={icon} size={18} /></span>
      <span className="media-lifecycle-content">
        <strong>{mediaLabel(message.mediaKind)}</strong>
        <small>{failed ? t("conversations.media_failed") : t("conversations.media_pending")}</small>
        {failed && <small className="media-lifecycle-reason">{t(reason)}</small>}
        {failed && message.mediaRetryable && <small>{t("conversations.media_retrying")}</small>}
      </span>
      {message.text && <p className="file-message-caption">{message.text}</p>}
    </div>
  );
}
