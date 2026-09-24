import { useEffect, useRef, useState } from "react";

import { Icon, LogoSpinner } from "../../shared/icons";
import { ComposerTemplatesMenu } from "./ComposerTemplatesMenu";
import { EmojiPicker } from "./EmojiPicker";
import { useMediaQuery } from "../../shared/useMediaQuery";
import { sendFileMessage, sendOperatorMessage, sendVoiceMessage } from "./model";
import { formatSize } from "../ai/knowledge/model";
import { formatDuration } from "./VoiceMessage";
import { TEMPLATE_VARIABLE_LABEL, unfilledVariables, type TemplateValues } from "./templateVariables";
import { useComposerTemplates } from "./useComposerTemplates";
import { useVoiceRecorder } from "./useVoiceRecorder";
import type { ChannelKey, ControlMode } from "./types";
import { t } from "../../i18n";

const MAX_FILE_BYTES = 20 * 1024 * 1024;

export function Composer({ mode, loaded, assignedOperatorName, conversationId, channel, voiceAllowed = true, templateValues = {}, onClaim, onRelease, onReturnQueue, onClose, onSent }: { mode: ControlMode; loaded: boolean; assignedOperatorName?: string; conversationId: number | null; channel?: ChannelKey; voiceAllowed?: boolean; templateValues?: TemplateValues; onClaim: () => void; onRelease: () => void; onReturnQueue: () => void; onClose: () => void; onSent: () => void }) {
  const [text, setText] = useState("");
  const compact = useMediaQuery("(max-width: 768px)");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Поле растёт под текст, как в мессенджере: до 7 строк, дальше скролл.
  // Композер прижат к низу ленты, поэтому рост идёт вверх.
  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = node.scrollHeight > 0 ? `${node.scrollHeight}px` : "";
  }, [text, attachment]);

  // Сброс черновика вложения при смене диалога.
  useEffect(() => { setAttachment(null); setSendError(""); }, [conversationId]);

  const templates = useComposerTemplates({ text, setText, values: templateValues, textareaRef });
  // Переменная шаблона без значения (у гостя нет имени) остаётся в тексте:
  // пока оператор её не заполнит, ответ не уходит.
  const unfilled = unfilledVariables(text);

  // Запись голосового: во всех каналах (TG/MAX sendVoice, почта — вложением, Web — поллингом).
  const recorder = useVoiceRecorder({
    onSend: async (audio, duration) => {
      if (conversationId == null) return;
      await sendVoiceMessage(conversationId, audio, duration);
      onSent();
    },
  });
  // Микрофон — если браузер умеет запись и голосовые разрешены в точке входа.
  const voiceAvailable = recorder.supported && voiceAllowed;

  if (conversationId == null) {
    return <div className="sales-composer"><div className="composer-locked"><div><strong>{t("conversations.pick_conversation")}</strong></div></div></div>;
  }

  if (!loaded) {
    return <div className="sales-composer"><div className="composer-locked is-loading"><LogoSpinner size={22} /></div></div>;
  }

  // Кадр E: закрытый диалог — композер заменён сообщением о закрытии.
  if (mode === "closed") {
    return (
      <div className="sales-composer"><div className="composer-locked">
        <span><Icon name="lock" size={19} /></span>
        <div><strong>{t("conversations.conversation_closed")}</strong><p>{t("conversations.history_kept_next_time_customer")}</p></div>
      </div></div>
    );
  }

  // Кадр D: ведёт другой сотрудник — композер заблокирован, взять можно явно.
  if (mode === "assigned") {
    return (
      <div className="sales-composer"><div className="composer-locked">
        <span><Icon name="lock" size={19} /></span>
        <div><strong>{assignedOperatorName ? t("conversations.handled_by", { name: assignedOperatorName }) : t("conversations.another_operator_handling_conversation")}</strong><p>{t("conversations.only_assignee_can_reply_take")}</p></div>
        <button className="composer-locked-action" type="button" onClick={onClaim}>{t("conversations.take_conversation")}</button>
      </div></div>
    );
  }

  // Вставка эмодзи в позицию курсора; фокус возвращается в поле.
  function insertEmoji(emoji: string) {
    const area = textareaRef.current;
    const start = area?.selectionStart ?? text.length;
    const end = area?.selectionEnd ?? text.length;
    const next = text.slice(0, start) + emoji + text.slice(end);
    setText(next);
    window.requestAnimationFrame(() => {
      if (!area) return;
      area.focus();
      area.setSelectionRange(start + emoji.length, start + emoji.length);
    });
  }

  async function send() {
    const value = text.trim();
    if ((!value && !attachment) || conversationId == null || sending || unfilled.length > 0) return;
    setSending(true);
    setSendError("");
    try {
      if (attachment) {
        // Файл уходит с подписью — текст поля становится подписью к файлу.
        await sendFileMessage(conversationId, attachment, value);
        setAttachment(null);
      } else {
        await sendOperatorMessage(conversationId, value);
      }
      setText("");
      onSent();
    } catch (error) {
      setSendError(error instanceof Error ? error.message : t("conversations.could_not_send_message"));
    } finally {
      setSending(false);
    }
  }

  function pickFile(file: File | null) {
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      setSendError(t("conversations.file_over_20_mb"));
      return;
    }
    setSendError("");
    setAttachment(file);
    textareaRef.current?.focus();
  }

  if (recorder.state !== "idle") {
    return (
      <div className="sales-composer">
        <div className="voice-recorder">
          <button aria-label={t("conversations.cancel_recording")} className="voice-recorder-cancel" title={t("conversations.cancel_recording")} type="button" onClick={recorder.cancel}>
            <Icon name="trash" size={16} />
          </button>
          <span className="voice-recorder-timer"><i />{formatDuration(recorder.seconds)}</span>
          <span className="voice-recorder-hint">
            {recorder.state === "sending" ? t("common.sending") : t("conversations.recording_esc_cancels_enter_sends")}
          </span>
          <button className="voice-recorder-send" disabled={recorder.state === "sending"} type="button" onClick={recorder.stopAndSend}>
            <Icon name="send" size={14} />{t("conversations.send")}</button>
        </div>
        {recorder.errorText && <div className="sales-composer-error">{recorder.errorText}</div>}
      </div>
    );
  }

  // Кадры A–C: композер активен всегда (решение 2) — первое сообщение
  // перехватывает диалог; над полем одна строка-предупреждение.
  const warning = unfilled.length > 0
    ? { color: "var(--warning-text)", dot: "var(--warning)", text: t("conversations.fill_template_variables", { names: unfilled.map((name) => t(TEMPLATE_VARIABLE_LABEL[name]).toLocaleLowerCase()).join(", ") }) }
    : mode === "ai"
    ? { color: "var(--ai)", text: t("conversations.ai_handling_conversation_message_takes") }
    : mode === "waiting"
      ? { color: "var(--warning-text)", dot: "var(--warning)", text: t("conversations.customer_waiting_message_assigns_conversation") }
      : null;

  return (
    <div className="sales-composer">
      <div className="composer-wrap">
        {warning && <div className="composer-warning" style={{ color: warning.color }}><i style={{ background: warning.dot ?? warning.color }} />{warning.text}</div>}
        <div className="composer-box">
          {templates.menuOpen && <ComposerTemplatesMenu items={templates.visible} onPick={templates.apply} />}
          {attachment && (
            <div className="composer-attachment">
              <Icon name="paperclip" size={14} />
              <strong title={attachment.name}>{attachment.name}</strong>
              <small>{formatSize(attachment.size)}</small>
              <button aria-label={t("common.remove_file")} title={t("common.remove_file")} type="button" disabled={sending} onClick={() => { setAttachment(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}>
                <Icon name="xCircle" size={15} />
              </button>
            </div>
          )}
          <textarea
            ref={textareaRef}
            rows={1}
            placeholder={attachment ? t("conversations.caption_file_optional") : compact ? t("conversations.message") : t("conversations.type_message_shift_enter_line")}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape" && templates.menuOpen) { templates.close(); if (templates.slashQuery !== null) setText(""); return; }
              if (event.key === "Enter" && !event.shiftKey) {
                if (templates.slashQuery !== null && templates.visible.length > 0) { event.preventDefault(); templates.apply(templates.visible[0]); return; }
                event.preventDefault();
                void send();
              }
            }}
            onBlur={templates.close}
            onPaste={(event) => {
              const file = Array.from(event.clipboardData?.files ?? [])[0];
              if (file) { event.preventDefault(); pickFile(file); }
            }}
          />
          <div className="composer-toolbar">
            <EmojiPicker onPick={insertEmoji} disabled={sending} />
            <button className="composer-tool" title={t("common.attach")} aria-label={t("common.attach_file")} type="button" disabled={sending} onClick={() => fileInputRef.current?.click()}>
              <Icon name="paperclip" size={17} />
            </button>
            <input ref={fileInputRef} type="file" hidden onChange={(event) => { pickFile(event.target.files?.[0] ?? null); event.target.value = ""; }} />
            {voiceAvailable && (
              <button className="composer-tool" title={t("conversations.record_voice_message")} aria-label={t("conversations.record_voice_message")} type="button" onClick={() => void recorder.start()}>
                <Icon name="mic" size={17} />
              </button>
            )}
            {templates.available && (
              <button className="composer-tool is-labeled" title={t("conversations.reply_templates")} type="button" onClick={templates.toggle}>
                <Icon name="text" size={16} />{t("conversations.templates")}</button>
            )}
            <span className="composer-spacer" />
            <button className="composer-send" type="button" onClick={() => void send()} disabled={sending || (!text.trim() && !attachment) || unfilled.length > 0}><span>{t("conversations.send")}</span><kbd>⏎</kbd><Icon name="send" size={17} /></button>
          </div>
        </div>
      </div>
      {sendError && <div className="sales-composer-error">{sendError}</div>}
    </div>
  );
}
