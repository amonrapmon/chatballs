import { t } from "../../i18n";
import { shortDateTime } from "../../shared/utils";
import type { EmailPayload } from "./instance";

export type EmailDraft = {
  host: string;
  port: string;
  user: string;
  password: string;
  useTls: boolean;
  from: string;
};

export function emailDraftOf(email: EmailPayload): EmailDraft {
  return {
    host: email.host,
    port: String(email.port || 587),
    user: email.user,
    password: "",
    useTls: email.useTls,
    from: email.from,
  };
}

export function savedLabel(updatedAt: string | null): string {
  if (!updatedAt) return t("common.never_saved_yet");
  return t("time.saved_at", { time: shortDateTime(updatedAt) });
}
