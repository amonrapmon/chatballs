import { useEffect, useRef, useState } from "react";

import { ApiError } from "../../api/client";
import { t } from "../../i18n";
import type { TokenEditorHandle } from "../reply-templates/TokenEditor";
import type { ComposerAudience } from "./ComposerAudienceBar";
import { useDraftMarkLayout } from "./ComposerDraftMark";
import { sendFileMessage, sendOperatorMessage, sendVoiceMessage } from "./model";
import { draftMark } from "./replyDraft";
import { unfilledVariables } from "./templateVariables";
import { useCommentSubmit } from "./useCommentSubmit";
import { useComposerTemplates } from "./useComposerTemplates";
import { useReplyAssistance } from "./useReplyAssistance";
import { useVoiceRecorder } from "./useVoiceRecorder";

const MAX_FILE_BYTES = 20 * 1024 * 1024;

/** Shared text, explicit audience and delivery through the audience's API. */
export function useComposerModel({ conversationId, onSent, onCommentSaved }: {
  conversationId: number | null;
  onSent: () => void;
  onCommentSaved: () => void;
}) {
  const [text, setText] = useState("");
  const [audience, setAudience] = useState<ComposerAudience>("reply");
  const [carriedToReply, setCarriedToReply] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  // Ключи, которые сервер назвал незаполненными при отправке.
  const [serverUnfilled, setServerUnfilled] = useState<string[]>([]);
  const editorRef = useRef<TokenEditorHandle>(null);
  const fieldRef = useRef<HTMLDivElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const comment = useCommentSubmit(conversationId, onCommentSaved);
  const isComment = audience === "comment";
  const busy = sending || comment.sending;
  const assist = useReplyAssistance(conversationId, setSendError);
  const { linked, unlink } = assist;
  const mark = !isComment && linked && text ? draftMark(linked.originalText, text) : null;

  useDraftMarkLayout(fieldRef, mirrorRef, [text, mark, audience]);
  useEffect(() => { if (!text) unlink(); }, [text, unlink]);
  // Текст с подставленными значениями относится к своему диалогу: в другой
  // диалог он не переносится.
  useEffect(() => { setAttachment(null); setText(""); setSendError(""); setServerUnfilled([]); }, [conversationId]);

  const templates = useComposerTemplates({
    text, conversationId, editorRef,
    setText: (next) => { unlink(); setText(next); setCarriedToReply(false); },
  });
  // Переменная шаблона без значения (у гостя нет имени) остаётся в тексте:
  // пока оператор её не заменит, текст не уходит ни клиенту, ни в комментарий.
  const unfilled = unfilledVariables(text, [...templates.unfilledKeys, ...serverUnfilled]);
  const recorder = useVoiceRecorder({
    onSend: async (audio, duration) => {
      if (conversationId == null) return;
      await sendVoiceMessage(conversationId, audio, duration);
      onSent();
    },
  });

  function switchAudience(next: ComposerAudience) {
    if (next === audience || busy) return;
    setAudience(next);
    setCarriedToReply(next === "reply" && text.trim() !== "");
    editorRef.current?.focus();
  }

  function changeText(next: string) {
    setText(next);
    if (!next.trim()) setCarriedToReply(false);
  }

  // Вставка в позицию курсора; фокус возвращается в поле.
  function insertEmoji(emoji: string) {
    editorRef.current?.insert(emoji);
  }

  async function send() {
    const value = text.trim();
    if (busy || unfilled.length > 0 || conversationId == null) return;
    if (isComment) {
      if (value && await comment.submit(value)) setText("");
      return;
    }
    if (!value && !attachment) return;
    setSending(true);
    setSendError("");
    try {
      if (attachment) {
        await sendFileMessage(conversationId, attachment, value);
        setAttachment(null);
      } else if (linked) {
        await assist.send(value);
      } else {
        await sendOperatorMessage(conversationId, value);
      }
      setText("");
      setCarriedToReply(false);
      onSent();
    } catch (error) {
      if (error instanceof ApiError && Array.isArray(error.payload.unfilledKeys)) {
        setServerUnfilled(error.payload.unfilledKeys.filter((key: unknown): key is string => typeof key === "string"));
      }
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
    editorRef.current?.focus();
  }

  function insertDraft() {
    if (isComment) return;
    const draft = assist.insert();
    if (draft == null) return;
    setText(draft);
    setCarriedToReply(false);
    editorRef.current?.focus();
  }

  return {
    text, changeText, audience, switchAudience, carriedToReply, isComment, busy,
    sendError, attachment, removeAttachment: () => setAttachment(null),
    editorRef, fieldRef, mirrorRef, comment, assist, mark, templates, unfilled, recorder,
    insertEmoji, send, pickFile, insertDraft,
  };
}