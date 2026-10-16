import { Icon } from "../../shared/icons";
import { ChannelGlyph } from "../../shared/badges";
import { ContactAvatar } from "./ContactAvatar";
import { PriorityBars } from "./DialogList";
import { modeDots } from "./data";
import type { ConversationListItem } from "./types";
import { t } from "../../i18n";

export function DialogListItem({ dialog, active, setSelectedId }: { dialog: ConversationListItem; active: boolean; setSelectedId: (id: number) => void }) {
  // Строка по дизайн-базлайну v2 (решение 4): канал + агент → имя · время →
  // превью (↩ если последнее сообщение наше) · непрочитанные → таймер ожидания,
  // группа, метки. Точка на аватаре — режим диалога.
  return (
    <button className={`sales-dialog-row ${active ? "active" : ""}`} onClick={() => setSelectedId(dialog.id)}>
      <span className="sales-dialog-avatar-wrap">
        <ContactAvatar avatarUrl={dialog.avatarUrl} initials={dialog.initials} background={dialog.avatarBg} className="sales-dialog-avatar" />
        <i style={{ background: modeDots[dialog.mode] }} />
      </span>
      <span className="sales-dialog-row-main">
        <span className="sales-dialog-row-agent">
          <small><ChannelGlyph provider={dialog.channel} /><span>{dialog.agentName}</span></small>
          {dialog.priority !== "NONE" && <PriorityBars priority={dialog.priority} />}
        </span>
        <span className="sales-dialog-row-title"><strong>{dialog.name}</strong><em>{dialog.time}</em></span>
        <span className="sales-dialog-row-preview">
          {dialog.lastIsOurs && <Icon name="reply" size={13} />}
          {dialog.lastIsVoice && <Icon name="mic" size={13} />}
          <small className={dialog.unread ? "unread" : ""}>{dialog.preview}</small>
          {dialog.unread > 0 && <b>{dialog.unread}</b>}
        </span>
        {(dialog.isParticipant || dialog.waitLabel || dialog.mineLabel || dialog.groupName || dialog.labels.length > 0) && (
          <span className="sales-dialog-row-badges">
            {dialog.isParticipant && <b className="sales-dialog-badge is-mine"><Icon name="team" size={11} />{t("participants.badge")}</b>}
            {dialog.waitLabel && <b className="sales-dialog-badge is-wait"><Icon name="clock" size={11} />{dialog.waitLabel}</b>}
            {dialog.mineLabel && <b className="sales-dialog-badge is-mine"><Icon name="user" size={11} />{dialog.mineLabel}</b>}
            {dialog.groupName && <b className="sales-dialog-badge"><i className="is-round" style={{ background: dialog.groupColor }} />{dialog.groupName}</b>}
            {dialog.labels.map((label) => (
              <b className="sales-dialog-badge" key={label.id}><i style={{ background: label.color || "var(--n-5)" }} />{label.name}</b>
            ))}
          </span>
        )}
      </span>
    </button>
  );
}
