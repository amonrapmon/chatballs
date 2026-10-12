import { Dropdown } from "antd";
import { useRef, type ReactNode, type RefObject } from "react";

import { Icon } from "../../shared/icons";
import { t } from "../../i18n";
import type { ComposerAudience } from "./ComposerAudienceBar";
import { ComposerTemplatesMenu } from "./ComposerTemplatesMenu";
import { EmojiPicker } from "./EmojiPicker";
import type { ComposerTemplatesState } from "./useComposerTemplates";

/** Инструменты под полем. У внутреннего комментария нет эмодзи, вложений и
 *  голосового (кадр C1) — остаются шаблоны и кнопка, названная по действию.
 *  Меню шаблонов — общий Dropdown, привязанный к рамке редактора: по макету
 *  (кадр T1) оно раскрывается над полем на всю его ширину. */
export function ComposerToolbar({ audience, busy, voiceAvailable, templates, boxRef, blocked, sendDisabled, onEmoji, onFile, onRecord, onSend, draftButton }: {
  draftButton?: ReactNode;
  audience: ComposerAudience;
  busy: boolean;
  voiceAvailable: boolean;
  templates: ComposerTemplatesState;
  boxRef: RefObject<HTMLDivElement | null>;
  /** В тексте осталась незаполненная переменная шаблона. */
  blocked: boolean;
  sendDisabled: boolean;
  onEmoji: (emoji: string) => void;
  onFile: (file: File | null) => void;
  onRecord: () => void;
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
      <Dropdown
        open={templates.menuOpen}
        onOpenChange={(open) => { if (open !== templates.menuOpen) templates.toggle(); }}
        trigger={["click"]}
        placement="topLeft"
        destroyOnHidden
        overlayClassName="app-dropdown reply-template-dropdown"
        getPopupContainer={() => boxRef.current ?? document.body}
        popupRender={() => <ComposerTemplatesMenu templates={templates} />}
      >
        <button className="composer-tool is-labeled" title={t("conversations.reply_templates")} type="button" disabled={busy}>
          <Icon name="text" size={16} />{t("conversations.templates")}
        </button>
      </Dropdown>
      {audience === "reply" && draftButton}
      <span className="composer-spacer" />
      <button className="composer-send" type="button" title={blocked ? t("templates.fill_variables_title") : sendLabel} onClick={onSend} disabled={sendDisabled}><span>{sendLabel}</span><kbd>⏎</kbd><Icon name="send" size={17} /></button>
    </div>
  );
}
