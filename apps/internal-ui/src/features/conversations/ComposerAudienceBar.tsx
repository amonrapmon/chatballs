import { Icon } from "../../shared/icons";
import { t } from "../../i18n";

export type ComposerAudience = "reply" | "email" | "comment";

/** Выбор аудитории до отправки (кадры C1, K2, M1): вкладка задаёт, кому уйдёт
 *  текст, подпись рядом называет получателя словами. */
export function ComposerAudienceBar({ audience, channelLabel, compact, onChange, email, replyDisabled = false, canComment = true }: { replyDisabled?: boolean; canComment?: boolean; email?: { recipient: string; available: boolean; busy: boolean }; audience: ComposerAudience; channelLabel: string; compact: boolean; onChange: (audience: ComposerAudience) => void }) {
  const tabs = [
    { key: "reply", icon: "message", label: compact ? t("comments.tab_reply_short") : t("comments.tab_reply"), title: t("comments.tab_reply") },
    ...(email ? [{ key: "email", icon: "mail", label: t("mail.tab"), title: email.available ? t("mail.tab") : t("mail.no_address_hint") } as const] : []),
    { key: "comment", icon: "lock", label: compact ? t("comments.tab_comment_short") : t("comments.tab_comment"), title: t("comments.tab_comment_hint") },
  ] as const;
  const internal = audience === "comment";
  return (
    <div className="composer-audience-bar">
      <div className="composer-tabs" role="tablist">
        {tabs.filter((tab) => tab.key !== "comment" || canComment).map((tab) => (
          <button key={tab.key} className={`composer-tab is-${tab.key}${tab.key === audience ? " is-active" : ""}${tab.key === "email" && !email?.available ? " is-unavailable" : ""}`} role="tab" aria-selected={tab.key === audience} title={tab.key === "reply" && replyDisabled ? t("supervision.reply_hint") : tab.title} type="button" disabled={email?.busy || (tab.key === "reply" && replyDisabled) || (tab.key === "email" && !email?.available)} onClick={() => onChange(tab.key)}>
            <Icon name={tab.icon} size={compact ? 13 : 14} strokeWidth={compact ? 2 : 1.9} />{tab.label}
          </button>
        ))}
      </div>
      <span className={`composer-audience is-${audience}`}>
        <Icon name={internal ? "lock" : audience === "email" ? "mail" : "user"} size={compact ? 12 : 13} strokeWidth={2} />
        <span>{internal ? t("comments.audience_staff") : audience === "email" ? t("mail.audience", { address: email?.recipient ?? "" }) : t("comments.audience_client", { channel: channelLabel })}</span>
      </span>
    </div>
  );
}
