import type { internalCommentsRu } from "./internal-comments.ru";

export const internalCommentsEn: Record<keyof typeof internalCommentsRu, string> = {
  "comments.add": "Add comment",
  "comments.audience_client": "Visible to the customer · {channel}",
  "comments.audience_staff": "Staff only — the customer will not see it",
  "comments.feed_actor": "{name} · internal comment",
  "comments.field_placeholder": "Comment for colleagues… The customer will not see it",
  "comments.not_saved_offline": "Comment not saved: no connection to the server.",
  "comments.switched_to_reply": "You switched to a customer reply — {name} will see this text.",
  "comments.tab_comment": "Comment",
  "comments.tab_comment_hint": "Internal comment — staff only",
  "comments.tab_comment_short": "Comment",
  "comments.tab_reply": "Reply to customer",
  "comments.tab_reply_short": "Customer",
};
