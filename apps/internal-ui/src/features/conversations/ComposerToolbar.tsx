import { useRef } from "react";

import { Icon } from "../../shared/icons";
import { t } from "../../i18n";
import type { ComposerAudience } from "./ComposerAudienceBar";
import { EmojiPicker } from "./EmojiPicker";

/** Инструменты под полем. У внутреннего комментария нет эмодзи, вложений и
 *  голосового (кадр C1) — остаются шаблоны и кнопка, названная по действию. */
export function ComposerToolbar({ audience, busy, voiceAvailable, templatesAvailable, sendDisabled, onEmoji, onFile, onRecord, onToggleTemplates, onSend }: {
  audience: ComposerAudience;
  busy: boolean;
  voiceAvailable: boolean;
  templatesAvailable: boolean;
  sendDisabled: boolean;
  onEmoji: (emoji: string) => void;
  onFile: (file: File | null) => void;
  onRecord: () => void;
  onToggleTemplates: () => void;
  onSend: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sendLabel = audience === "comment" ? t("comments.add") : t("conversations.send");
  return (
    <div className="composer-toolbar">
      {audience === "reply" && (
        <>
          <EmojiPicker onPick={onEmoji} disabled={busy} />
          <button className="composer-tool" title={t("common.attach")} aria-label={t("common.attach_file")} type="button" disabled={busy} onClick={() => fileInputRef.current?.click()}>
            <Icon name="paperclip" size={17} />
          </button>
          <input ref={fileInputRef} type="file" hidden onChange={(event) => { onFile(event.target.files?.[0] ?? null); event.target.value = ""; }} />
          {voiceAvailable && (
            <button className="composer-tool" title={t("conversations.record_voice_message")} aria-label={t("conversations.record_voice_message")} type="button" onClick={onRecord}>
              <Icon name="mic" size={17} />
            </button>
          )}
        </>
      )}
      {templatesAvailable && (
        <button className="composer-tool is-labeled" title={t("conversations.reply_templates")} type="button" onClick={onToggleTemplates}>
          <Icon name="text" size={16} />{t("conversations.templates")}</button>
      )}
      <span className="composer-spacer" />
      <button className="composer-send" type="button" title={sendLabel} onClick={onSend} disabled={sendDisabled}><span>{sendLabel}</span><kbd>⏎</kbd><Icon name="send" size={17} /></button>
    </div>
  );
}
