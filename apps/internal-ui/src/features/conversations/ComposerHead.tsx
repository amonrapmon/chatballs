import { Icon } from "../../shared/icons";
import { providerMeta } from "../../shared/providers";
import type { ChannelKey } from "./types";
import { t } from "../../i18n";

// Шапка редактора (макет «Редактор ответа»): вкладка режима и подпись о том,
// кто увидит текст. Режим пока один — ответ клиенту.
export function ComposerHead({ channel }: { channel?: ChannelKey }) {
  return (
    <div className="composer-head" role="tablist">
      <button className="composer-tab is-active" type="button" role="tab" aria-selected="true">
        <Icon name="message" size={14} strokeWidth={1.9} />{t("conversations.reply_to_customer")}
      </button>
      <span className="composer-spacer" />
      {channel && (
        <span className="composer-audience">
          <Icon name="user" size={13} strokeWidth={2} />
          <span>{t("conversations.customer_will_see", { channel: providerMeta[channel].label })}</span>
        </span>
      )}
    </div>
  );
}
