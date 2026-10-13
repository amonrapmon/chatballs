import { useRef } from "react";

import { t } from "../../i18n";
import { pathFromRoute } from "../../router";
import { EmailComposerFields } from "./EmailComposerFields";
import { providerMeta } from "../../shared/providers";
import { useMediaQuery } from "../../shared/useMediaQuery";
import { TokenEditor } from "../reply-templates/TokenEditor";
import { ComposerAttachment } from "./ComposerAttachment";
import { ComposerAudienceBar } from "./ComposerAudienceBar";
import { ComposerDraftButton } from "./ComposerDraftButton";
import { ComposerDraftMark } from "./ComposerDraftMark";
import { ComposerDraftPanel } from "./ComposerDraftPanel";
import { ComposerFoot } from "./ComposerFoot";
import { ComposerLocked } from "./ComposerLocked";
import { ComposerToolbar } from "./ComposerToolbar";
import { ComposerVoiceRecorder } from "./ComposerVoiceRecorder";
import { ComposerWarning } from "./ComposerWarning";
import type { ChannelKey, ControlMode } from "./types";
import { useComposerModel } from "./useComposerModel";
import "./template-picker.css";

export function Composer({ mode, loaded, assignedOperatorName, isParticipant = false, conversationId, contactId, clientName, channel, voiceAllowed = true, assistanceEnabled = false, agentName = "", onClaim, onSent, onCommentSaved }: {
  mode: ControlMode; loaded: boolean; assignedOperatorName?: string; isParticipant?: boolean;
  conversationId: number | null; contactId?: number; clientName: string; channel?: ChannelKey;
  voiceAllowed?: boolean;
  assistanceEnabled?: boolean; agentName?: string;
  onClaim: () => void; onRelease: () => void; onReturnQueue: () => void;
  onClose: () => void; onSent: () => void; onCommentSaved: () => void;
}) {
  const compact = useMediaQuery("(max-width: 768px)");
  const boxRef = useRef<HTMLDivElement>(null);
  const model = useComposerModel({ conversationId, onSent, onCommentSaved });
  const { text, isComment, isEmail, email, assist, templates, unfilled, mark } = model;
  const noAddress = Boolean(email.options && !email.options.addresses.length);

  if (conversationId == null) return <ComposerLocked icon={false} title={t("conversations.pick_conversation")} />;
  if (!loaded) return <ComposerLocked loading />;
  if (mode === "closed") return <ComposerLocked title={t("conversations.conversation_closed")} text={t("conversations.history_kept_next_time_customer")} />;
  if (mode === "assigned") {
    return <ComposerLocked title={assignedOperatorName ? t("conversations.handled_by", { name: assignedOperatorName }) : t("conversations.another_operator_handling_conversation")} text={t("conversations.only_assignee_can_reply_take")} action={<button className="composer-locked-action" type="button" onClick={onClaim}>{t("conversations.take_conversation")}</button>} />;
  }
  if (model.recorder.state !== "idle") return <ComposerVoiceRecorder recorder={model.recorder} />;

  const placeholder = isEmail ? t("mail.text_placeholder") : isComment ? t("comments.field_placeholder") : model.attachment ? t("conversations.caption_file_optional") : compact ? t("conversations.message") : t("conversations.type_message_shift_enter_line");
  const foot = mark ? t("conversations.draft_sent_as_you") : assist.rejected ? t("conversations.draft_rejected") : "";
  const draftState = !assistanceEnabled ? "off" : assist.busy ? "busy" : assist.view ? "active" : "idle";
  const unfilledNames = unfilled.map((key) => templates.variables.find((variable) => variable.key === key)?.label ?? `{{${key}}}`).join("», «");

  return (
    <div className="sales-composer">
      <div className="composer-wrap">
        <ComposerWarning mode={mode} internal={isComment} />
        <div className={`composer-box${isComment ? " is-comment" : ""}`} ref={boxRef}>
          <ComposerAudienceBar audience={model.audience} channelLabel={channel ? providerMeta[channel].label : ""} compact={compact} onChange={model.switchAudience} email={channel === "WEB" ? { recipient: email.recipient, available: Boolean(email.options && !noAddress), busy: model.busy } : undefined} />
          {isEmail && email.options && <EmailComposerFields options={email.options} recipient={email.recipient} mailbox={email.mailbox} subject={email.subject} disabled={model.busy}
            onRecipient={email.setRecipient} onMailbox={email.setConnectionId} onSubject={email.setSubject} />}
          {!isComment && !isEmail && assist.view && <ComposerDraftPanel view={assist.view} rejecting={assist.rejecting} onSelect={assist.select} onInsert={model.insertDraft} onRephrase={assist.rephrase} onRetry={assist.retry} onReject={assist.reject} onDismiss={assist.dismiss} />}
          {model.attachment && !isComment && <ComposerAttachment file={model.attachment} disabled={model.busy} onRemove={model.removeAttachment} />}
          <div className="composer-field">
            <TokenEditor
              editorRef={model.editorRef}
              fieldRef={model.fieldRef}
              label={t(isEmail ? "mail.text" : "conversations.message")}
              disabled={model.busy}
              placeholder={placeholder}
              value={text}
              variables={templates.variables}
              invalidKeys={unfilled}
              chipKeys={unfilled}
              onChange={model.changeText}
              onKeyDown={(event) => {
                if (event.key === "Escape" && templates.menuOpen) { event.preventDefault(); templates.escape(); return; }
                if (templates.menuOpen && (event.key === "ArrowUp" || event.key === "ArrowDown")) { event.preventDefault(); templates.move(event.key === "ArrowDown" ? 1 : -1); return; }
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (templates.menuOpen) templates.applySelected();
                  else void model.send();
                }
              }}
              onPaste={(event) => {
                const file = Array.from(event.clipboardData?.files ?? [])[0];
                if (file && !isComment) { event.preventDefault(); model.pickFile(file); }
              }}
            />
            {mark && <ComposerDraftMark text={text} label={mark} ref={model.mirrorRef} />}
            <ComposerToolbar
              audience={model.audience}
              busy={model.busy}
              voiceAvailable={model.recorder.supported && voiceAllowed && !isEmail}
              templates={templates}
              boxRef={boxRef}
              blocked={unfilled.length > 0}
              sendDisabled={model.busy || templates.applying || unfilled.length > 0 || (!text.trim() && (isComment || !model.attachment)) || (isEmail && email.blocked)}
              onEmoji={model.insertEmoji}
              onFile={model.pickFile}
              onRecord={() => void model.recorder.start()}
              onSend={() => void model.send()}
              draftButton={!isEmail && <ComposerDraftButton state={draftState} agentName={agentName} onRequest={assist.request} />}
            />
          </div>
        </div>
        {channel === "WEB" && noAddress && <div className="email-composer-foot"><i /><span>{t("mail.no_address")} {contactId && <a className="link" href={pathFromRoute("salesClientDetail", contactId)}>{t("mail.add_address")}</a>}</span></div>}
        {isEmail && email.options && !email.options.mailboxes.length && <div className="email-composer-foot is-error"><i /><span>{t("mail.no_mailbox_hint")}</span></div>}
        {/* Кадр T3: значения нет — переменная подсвечена, отправка ждёт правки. */}
        {unfilled.length > 0 && <ComposerFoot tone="error" text={t("templates.fill_variables", { names: unfilledNames })} />}
        {isComment && model.comment.errorText && text.trim() !== "" && <ComposerFoot tone="error" text={model.comment.errorText} actionLabel={t("common.try_again")} onAction={() => void model.send()} />}
        {!isComment && model.carriedToReply && text.trim() !== "" && <ComposerFoot tone="warning" text={t("comments.switched_to_reply", { name: clientName })} />}
        {isParticipant && <div className="composer-foot is-participant"><i /><span>{t("participants.reply_hint", { name: assignedOperatorName ?? "" })}</span></div>}
        {!isComment && !isEmail && foot && <div className="composer-foot"><i /><span>{foot}</span></div>}
      </div>
      {templates.error && <div className="sales-composer-error" role="alert">{templates.error}</div>}
      {model.sendError && !isComment && <div className="sales-composer-error">{model.sendError}</div>}
    </div>
  );
}
