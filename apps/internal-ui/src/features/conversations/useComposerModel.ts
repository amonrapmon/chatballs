import { useEffect, useRef, useState } from "react";

import { t } from "../../i18n";
import type { ComposerAudience } from "./ComposerAudienceBar";
import { fitTextareaHeight, useDraftMarkLayout } from "./ComposerDraftMark";
import { sendFileMessage, sendOperatorMessage, sendVoiceMessage } from "./model";
import { draftMark } from "./replyDraft";
import { unfilledVariables, type TemplateValues } from "./templateVariables";
import { useCommentSubmit } from "./useCommentSubmit";
import { useComposerTemplates } from "./useComposerTemplates";
import { useReplyAssistance } from "./useReplyAssistance";
import { useVoiceRecorder } from "./useVoiceRecorder";

const MAX_FILE_BYTES = 20 * 1024 * 1024;

/** Shared text, explicit audience and delivery through the audience's API. */
export function useComposerModel({ conversationId, templateValues, onSent, onCommentSaved }: {
  conversationId: number | null;
  templateValues: TemplateValues;
  onSent: () => void;
  onCommentSaved: () => void;
}) {
  const [text, setText] = useState("");
  const [audience, setAudience] = useState<ComposerAudience>("reply");
  const [carriedToReply, setCarriedToReply] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mirrorRef = useRef<HTMLDivElement>(null);
  const comment = useCommentSubmit(conversationId, onCommentSaved);
  const isComment = audience === "comment";
  const busy = sending || comment.sending;
  const assist = useReplyAssistance(conversationId, setSendError);
  const { linked, unlink } = assist;
  const mark = !isComment && linked && text ? draftMark(linked.originalText, text) : null;

  useEffect(() => {
    if (textareaRef.current) fitTextareaHeight(textareaRef.current);
  }, [text, attachment, audience]);
  useDraftMarkLayout(textareaRef, mirrorRef, [text, mark, audience]);
  useEffect(() => { if (!text) unlink(); }, [text, unlink]);
  useEffect(() => { setAttachment(null); setSendError(""); }, [conversationId]);

  const templates = useComposerTemplates({
    text, values: templateValues, textareaRef,
    setText: (next) => { unlink(); setText(next); setCarriedToReply(false); },
  });
  const unfilled = unfilledVariables(text);
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
    textareaRef.current?.focus();
  }

  function changeText(next: string) {
    setText(next);
    if (!next.trim()) setCarriedToReply(false);
  }

  function insertEmoji(emoji: string) {
    const area = textareaRef.current;
    const start = area?.selectionStart ?? text.length;
    const end = area?.selectionEnd ?? text.length;
    setText(text.slice(0, start) + emoji + text.slice(end));
    window.requestAnimationFrame(() => {
      area?.focus();
      area?.setSelectionRange(start + emoji.length, start + emoji.length);
    });
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

  function insertDraft() {
    if (isComment) return;
    const draft = assist.insert();
    if (draft == null) return;
    setText(draft);
    setCarriedToReply(false);
    textareaRef.current?.focus();
  }

  return {
    text, changeText, audience, switchAudience, carriedToReply, isComment, busy,
    sendError, attachment, removeAttachment: () => setAttachment(null),
    textareaRef, mirrorRef, comment, assist, mark, templates, unfilled, recorder,
    insertEmoji, send, pickFile, insertDraft,
  };
}