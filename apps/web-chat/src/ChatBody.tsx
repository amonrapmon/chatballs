import type { RefObject } from "react";
import type { WebConfig, WebMessage } from "./api";
import { BotAvatar } from "./BotIcon";
import { Bubble, SystemMessage, Typing } from "./ChatMessages";
import { ConsentText } from "./ConsentText";
import { PhoneForm } from "./PhoneForm";
import { t } from "./i18n";
import { widgetClasses as classes } from "./widgetClasses";

export function ChatBody({ bodyRef, config, unavailable, accepted, accent, title, messages, pending, awaiting, lastContactRequestId, showPhoneForm, onSubmitContact, audioUrlFor, attachmentUrlFor }: {
  bodyRef: RefObject<HTMLDivElement | null>;
  config: WebConfig | null;
  unavailable: boolean;
  accepted: boolean;
  accent: string;
  title: string;
  messages: WebMessage[];
  pending: string[];
  awaiting: boolean;
  lastContactRequestId: number;
  showPhoneForm: boolean;
  onSubmitContact: (phone: string) => Promise<boolean>;
  audioUrlFor?: (messageId: number) => string;
  attachmentUrlFor?: (messageId: number, inline: boolean) => string;
}) {
  return (
    <div ref={bodyRef} className={classes.body}>
      {config === null && <div style={{ textAlign: "center", color: "#8c8c8c", padding: 24, fontSize: 13 }}>{t("chat.loading")}</div>}
      {unavailable && <Unavailable />}
      {config?.available && !accepted && <Consent config={config} accent={accent} title={title} />}
      {config?.available && accepted && (
        <>
          <div style={{ textAlign: "center", marginBottom: 14 }}><span style={{ display: "inline-block", padding: "3px 11px", borderRadius: 20, background: "#eef0f2", fontSize: 11, color: "#8c8c8c" }}>{t("chat.today")}</span></div>
          {config.greeting && <Bubble author="ai" text={config.greeting} accent={accent} authorName={title} />}
          {messages.map((message) => message.author === "system"
            ? <SystemMessage key={message.id} text={message.text} />
            : <div key={message.id}><Bubble author={message.author} authorName={title} text={message.hasAudio ? "" : message.text || (message.kind === "voice" ? t("chat.voice_message") : "")} accent={accent} time={message.createdAt} audioUrl={message.hasAudio && audioUrlFor ? audioUrlFor(message.id) : undefined} voice={{ messageId: message.id, durationSeconds: message.durationSeconds }} attachment={message.kind === "file" && message.attachment ? { ...message.attachment, url: message.attachment.available && attachmentUrlFor ? attachmentUrlFor(message.id, false) : "", inlineUrl: message.attachment.available && attachmentUrlFor ? attachmentUrlFor(message.id, true) : "" } : undefined} />{message.kind === "contact_request" && message.id === lastContactRequestId && showPhoneForm && <PhoneForm accent={accent} onSubmit={onSubmitContact} />}</div>)}
          {pending.map((text, index) => <Bubble key={`p${index}`} author="client" authorName={title} text={text} accent={accent} pendingState />)}
          {awaiting && <Typing accent={accent} authorName={title} />}
        </>
      )}
    </div>
  );
}

function Unavailable() {
  return <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: "26px 14px" }}><div style={{ width: 52, height: 52, borderRadius: "50%", background: "#fff7e6", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 14 }}><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="#d48806" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg></div><h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>{t("chat.unavailable_title")}</h3><p style={{ margin: "8px 0 0", fontSize: 13, color: "#595959", lineHeight: 1.5, maxWidth: 280 }}>{t("chat.unavailable_body")}</p></div>;
}

function Consent({ config, accent, title }: { config: WebConfig; accent: string; title: string }) {
  return <><div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: "20px 12px 8px" }}><div style={{ marginBottom: 14 }}><BotAvatar size={56} accent={accent} /></div><h3 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>{title}</h3><p style={{ margin: "8px 0 0", fontSize: 15.5, lineHeight: "22px", color: "#595959", maxWidth: 300 }}>{config.greeting}</p></div><div style={{ marginTop: 18, background: "#fff", border: "1px solid #f0f0f0", borderRadius: 12, padding: 14 }}><ConsentText consent={config.consent} place="screen" /></div></>;
}

