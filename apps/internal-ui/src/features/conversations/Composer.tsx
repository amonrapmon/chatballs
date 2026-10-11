import { useEffect, useRef, useState } from "react";

import { providerMeta } from "../../shared/providers";
import { ComposerAttachment } from "./ComposerAttachment";
import { ComposerAudienceBar, type ComposerAudience } from "./ComposerAudienceBar";
import { ComposerFoot } from "./ComposerFoot";
import { ComposerLocked } from "./ComposerLocked";
import { ComposerTemplatesMenu } from "./ComposerTemplatesMenu";
import { ComposerToolbar } from "./ComposerToolbar";
import { ComposerVoiceRecorder } from "./ComposerVoiceRecorder";
import { useMediaQuery } from "../../shared/useMediaQuery";
import { sendFileMessage, sendOperatorMessage, sendVoiceMessage } from "./model";
import { TEMPLATE_VARIABLE_LABEL, unfilledVariables, type TemplateValues } from "./templateVariables";
import { useCommentSubmit } from "./useCommentSubmit";
import { useComposerTemplates } from "./useComposerTemplates";
import { useVoiceRecorder } from "./useVoiceRecorder";
import type { ChannelKey, ControlMode } from "./types";
import { t } from "../../i18n";

const MAX_FILE_BYTES = 20 * 1024 * 1024;

export function Composer({ mode, loaded, assignedOperatorName, conversationId, clientName, channel, voiceAllowed = true, templateValues = {}, onClaim, onSent, onCommentSaved }: { mode: ControlMode; loaded: boolean; assignedOperatorName?: string; conversationId: number | null; clientName: string; channel: ChannelKey; voiceAllowed?: boolean; templateValues?: TemplateValues; onClaim: () => void; onRelease: () => void; onReturnQueue: () => void; onClose: () => void; onSent: () => void; onCommentSaved: () => void }) {
  // Текст у вкладок общий (кадр C4), а аудитория выбирается явно и до отправки:
  // от неё зависит и маршрут запроса, и то, увидит ли текст клиент.
  const [text, setText] = useState("");
  const [audience, setAudience] = useState<ComposerAudience>("reply");
  const [carriedToReply, setCarriedToReply] = useState(false);
  const compact = useMediaQuery("(max-width: 768px)");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const comment = useCommentSubmit(conversationId, onCommentSaved);
  const isComment = audience === "comment";
  const busy = sending || comment.sending;

  // Поле растёт под текст, как в мессенджере: до 7 строк, дальше скролл.
  // Композер прижат к низу ленты, поэтому рост идёт вверх.
  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = node.scrollHeight > 0 ? `${node.scrollHeight}px` : "";
  }, [text, attachment, audience]);

  // Сброс черновика вложения при смене диалога.
  useEffect(() => { setAttachment(null); setSendError(""); }, [conversationId]);

  const templates = useComposerTemplates({ text, setText: (value) => { setText(value); setCarriedToReply(false); }, values: templateValues, textareaRef });
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

  if (conversationId == null) return <ComposerLocked icon={false} title={t("conversations.pick_conversation")} />;
  if (!loaded) return <ComposerLocked loading />;
  // Кадр E: закрытый диалог — композер заменён сообщением о закрытии.
  if (mode === "closed") return <ComposerLocked title={t("conversations.conversation_closed")} text={t("conversations.history_kept_next_time_customer")} />;
  // Кадр D: ведёт другой сотрудник — композер заблокирован, взять можно явно.
  if (mode === "assigned") {
    return (
      <ComposerLocked
        title={assignedOperatorName ? t("conversations.handled_by", { name: assignedOperatorName }) : t("conversations.another_operator_handling_conversation")}
        text={t("conversations.only_assignee_can_reply_take")}
        action={<button className="composer-locked-action" type="button" onClick={onClaim}>{t("conversations.take_conversation")}</button>}
      />
    );
  }
  if (recorder.state !== "idle") return <ComposerVoiceRecorder recorder={recorder} />;

  function switchAudience(next: ComposerAudience) {
    // Пока запрос в пути, аудитория не меняется: его текст уже ушёл своим маршрутом.
    if (next === audience || busy) return;
    setAudience(next);
    setCarriedToReply(next === "reply" && text.trim() !== "");
    textareaRef.current?.focus();
  }

  // Вставка эмодзи в позицию курсора; фокус возвращается в поле.
  function insertEmoji(emoji: string) {
    const area = textareaRef.current;
    const start = area?.selectionStart ?? text.length;
    const end = area?.selectionEnd ?? text.length;
    setText(text.slice(0, start) + emoji + text.slice(end));
    window.requestAnimationFrame(() => {
      if (!area) return;
      area.focus();
      area.setSelectionRange(start + emoji.length, start + emoji.length);
    });
  }

  async function send() {
    const value = text.trim();
    if (busy || unfilled.length > 0 || conversationId == null) return;
    if (isComment) {
      // Комментарий уходит только своим маршрутом; вложение ответа к нему не относится.
      if (value && await comment.submit(value)) setText("");
      return;
    }
    if (!value && !attachment) return;
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
      setCarriedToReply(false);
      onSent();
    } catch (error) {
      setSendError(error instanceof Error ? error.message : t("conversations.could_not_send_message"));
    } finally {
      setSending(false);
    }
  }

  function pickFile(file: File | null) {
    if (!file || isComment) return;
    if (file.size > MAX_FILE_BYTES) {
      setSendError(t("conversations.file_over_20_mb"));
      return;
    }
    setSendError("");
    setAttachment(file);
    textareaRef.current?.focus();
  }

  // Кадры A–C: композер активен всегда (решение 2) — первое сообщение
  // перехватывает диалог; над полем одна строка-предупреждение. Комментарий
  // диалог не перехватывает, поэтому предупреждений о перехвате у него нет.
  const warning = unfilled.length > 0
    ? { color: "var(--warning-text)", dot: "var(--warning)", text: t("conversations.fill_template_variables", { names: unfilled.map((name) => t(TEMPLATE_VARIABLE_LABEL[name]).toLocaleLowerCase()).join(", ") }) }
    : isComment
      ? null
      : mode === "ai"
        ? { color: "var(--ai)", text: t("conversations.ai_handling_conversation_message_takes") }
        : mode === "waiting"
          ? { color: "var(--warning-text)", dot: "var(--warning)", text: t("conversations.customer_waiting_message_assigns_conversation") }
          : null;
  const placeholder = isComment
    ? t("comments.field_placeholder")
    : attachment ? t("conversations.caption_file_optional") : compact ? t("conversations.message") : t("conversations.type_message_shift_enter_line");

  return (
    <div className="sales-composer">
      <div className="composer-wrap">
        {warning && <div className="composer-warning" style={{ color: warning.color }}><i style={{ background: warning.dot ?? warning.color }} />{warning.text}</div>}
        <div className={`composer-box${isComment ? " is-comment" : ""}`}>
          {templates.menuOpen && <ComposerTemplatesMenu items={templates.visible} onPick={templates.apply} />}
          <ComposerAudienceBar audience={audience} channelLabel={providerMeta[channel].label} compact={compact} onChange={switchAudience} />
          {attachment && !isComment && <ComposerAttachment file={attachment} disabled={sending} onRemove={() => setAttachment(null)} />}
          <div className="composer-field">
            <textarea
              ref={textareaRef}
              rows={1}
              placeholder={placeholder}
              value={text}
              onChange={(event) => { setText(event.target.value); if (!event.target.value.trim()) setCarriedToReply(false); }}
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
                if (file && !isComment) { event.preventDefault(); pickFile(file); }
              }}
            />
            <ComposerToolbar audience={audience} busy={busy} voiceAvailable={voiceAvailable} templatesAvailable={templates.available} sendDisabled={busy || unfilled.length > 0 || (!text.trim() && (isComment || !attachment))} onEmoji={insertEmoji} onFile={pickFile} onRecord={() => void recorder.start()} onToggleTemplates={templates.toggle} onSend={() => void send()} />
          </div>
        </div>
        {isComment && comment.errorText && text.trim() !== "" && <ComposerFoot tone="error" text={comment.errorText} actionLabel={t("common.try_again")} onAction={() => void send()} />}
        {!isComment && carriedToReply && text.trim() !== "" && <ComposerFoot tone="warning" text={t("comments.switched_to_reply", { name: clientName })} />}
      </div>
      {sendError && !isComment && <div className="sales-composer-error">{sendError}</div>}
    </div>
  );
}
