import { useEffect, useRef, useState } from "react";

import {
  declineWebchatCall,
  getConfig,
  openWebchatCall,
  poll,
  SessionExpired,
  sendContact,
  sendMessage,
  sendFile,
  sendVoice,
  attachmentUrl,
  MAX_FILE_BYTES,
  startSession,
  voiceAudioUrl,
  type CallInfo,
  type Poll,
  type WebConfig,
  type WebMessage,
} from "./api";
import { BrandFooter } from "./BrandFooter";
import { CallInviteBanner, ChatBody, ChatComposer, ChatHeader, StartChatFooter } from "./ChatView";
import { usePanelFullscreen } from "./usePanelFullscreen";
import { useScrollToLatest } from "./useScrollToLatest";
import { useVoiceRecorder } from "./useVoiceRecorder";
import { useWidgetActivity } from "./widgetActivity";
import { applyWidgetLanguage, t } from "./i18n";

const PARAMS = new URLSearchParams(location.search);
const WIDGET_KEY = PARAMS.get("widgetKey") || "";
const LEGACY_CHANNEL = PARAMS.get("channel") || "";
const ENTRY = WIDGET_KEY ? { widgetKey: WIDGET_KEY } : { channel: LEGACY_CHANNEL };
const HOST_ORIGIN = document.referrer ? new URL(document.referrer).origin : location.origin;
const TOKEN_KEY = `chatballs-chat-token:${WIDGET_KEY || `channel:${LEGACY_CHANNEL}`}`;

function closePanel() {
  window.parent.postMessage({ type: "chatballs-chat-close" }, "*");
}

/** Размер окна держит лоадер: панель живёт в iframe и сама себя не растянет. */
function requestExpanded(expanded: boolean) {
  window.parent.postMessage({ type: "chatballs-chat-expand", expanded }, "*");
}

export function App() {
  const [config, setConfig] = useState<WebConfig | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [accepted, setAccepted] = useState<boolean>(() => Boolean(localStorage.getItem(TOKEN_KEY)));
  const [messages, setMessages] = useState<WebMessage[]>([]);
  const [pending, setPending] = useState<string[]>([]);
  const [state, setState] = useState<"ai" | "operator" | "waiting">("ai");
  const [awaiting, setAwaiting] = useState(false);
  // Ответ считается на сервере и приедет следующим опросом: до тех пор в ленте
  // висит «печатает».
  const [thinking, setThinking] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [input, setInput] = useState("");
  const [starting, setStarting] = useState(false);
  const [contactSent, setContactSent] = useState(false);
  const [attachment, setAttachment] = useState<File | null>(null);
  const [attachmentError, setAttachmentError] = useState("");
  const [call, setCall] = useState<CallInfo | null>(null);
  const lastId = useRef(0);
  const openedCallId = useRef("");
  const pollingReady = useRef(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const scrollToLatest = useScrollToLatest(bodyRef);
  const fullscreen = usePanelFullscreen();
  const incomingCall = Boolean(call && (call.status === "REQUESTED" || call.status === "RINGING"));
  const notifyNewMessage = useWidgetActivity(incomingCall);
  const recorder = useVoiceRecorder({
    onSend: async (audio, durationSeconds) => {
      if (!token) return;
      const ok = await sendVoice(token, audio, durationSeconds);
      if (!ok) throw new Error(t("chat.could_not_send_voice"));
      try { ingestPoll(await poll(token, lastId.current)); } catch { /* polling loop will retry */ }
    },
  });

  useEffect(() => {
    getConfig(ENTRY, HOST_ORIGIN)
      .then((loaded) => {
        // Язык приходит вместе с настройками. Ставится до setConfig: рендер,
        // который они вызовут, уже пройдёт на нужном языке.
        applyWidgetLanguage(loaded.language);
        setConfig(loaded);
      })
      .catch(() => setConfig({ available: false }));
  }, []);

  function ingestPoll(data: Poll, notify = true) {
    // Диалог удалили на стороне поддержки — переписка обнуляется, и виджет
    // продолжает жить как только что открытый.
    if (data.reset) {
      lastId.current = 0;
      setMessages([]);
      setPending([]);
      setAwaiting(false);
      setContactSent(false);
    }
    setState(data.state);
    setThinking(Boolean(data.thinking));
    setCall(data.call?.callId === openedCallId.current ? null : (data.call ?? null));
    if (!data.messages.length) return;
    if (notify && data.messages.some((message) => message.author === "ai" || message.author === "operator")) notifyNewMessage();
    lastId.current = Math.max(lastId.current, ...data.messages.map((message) => message.id));
    setMessages((previous) => [...previous, ...data.messages.filter((message) => !previous.some((existing) => existing.id === message.id))]);
    if (data.messages.some((message) => message.author !== "client")) setAwaiting(false);
    setPending([]);
  }

  useEffect(() => {
    if (!accepted || !token) return;
    let alive = true;
    const tick = async () => {
      try {
        const data = await poll(token, lastId.current);
        if (alive) {
          ingestPoll(data, pollingReady.current);
          pollingReady.current = true;
        }
      } catch (error) {
        // Сессия истекла — иначе виджет молча висел бы с мёртвым токеном.
        if (alive && error instanceof SessionExpired) forgetSession();
        /* остальное — сеть или лимит: продолжаем опрашивать */
      }
    };
    void tick();
    const timer = setInterval(tick, 2500);
    return () => { alive = false; clearInterval(timer); };
  }, [accepted, token]);

  useEffect(() => {
    scrollToLatest();
  }, [scrollToLatest, messages, pending, awaiting]);

  const accent = config?.accent || "#1677ff";
  const title = config?.title || t("chat.chat");

  function toggleExpanded() {
    setExpanded((previous) => {
      requestExpanded(!previous);
      return !previous;
    });
  }

  function forgetSession() {
    localStorage.removeItem(TOKEN_KEY);
    lastId.current = 0;
    pollingReady.current = false;
    setToken(null);
    setAccepted(false);
    setMessages([]);
    setPending([]);
    setAwaiting(false);
    setThinking(false);
    setCall(null);
    setContactSent(false);
  }

  async function accept() {
    setStarting(true);
    const nextToken = await startSession(ENTRY, HOST_ORIGIN);
    setStarting(false);
    if (!nextToken) return;
    localStorage.setItem(TOKEN_KEY, nextToken);
    setToken(nextToken);
    setAccepted(true);
  }

  async function send() {
    const text = input.trim();
    if ((!text && !attachment) || !token || awaiting) return;
    setInput("");
    const file = attachment;
    setAttachment(null);
    setAttachmentError("");
    setPending((previous) => [...previous, file ? `${file.name}${text ? ` · ${text}` : ""}` : text]);
    setAwaiting(true);
    if (file) {
      const ok = await sendFile(token, file, text).catch(() => false);
      if (!ok) setAttachmentError(t("chat.could_not_send_file"));
    } else {
      await sendMessage(token, text).catch(() => undefined);
    }
    try { ingestPoll(await poll(token, lastId.current)); } catch { /* polling loop will retry */ }
    setPending([]);
    setAwaiting(false);
  }

  async function submitContact(phone: string): Promise<boolean> {
    if (!token) return false;
    const ok = await sendContact(token, phone).catch(() => false);
    if (ok) {
      setContactSent(true);
      try { ingestPoll(await poll(token, lastId.current)); } catch { /* polling loop will retry */ }
    }
    return ok;
  }

  async function acceptCallInvite() {
    if (!token) return;
    const opened = await openWebchatCall(token).catch(() => null);
    if (!opened) { setCall(null); return; }
    openedCallId.current = opened.call.callId;
    setCall(null);
    window.open(`/calls/${opened.call.callId}?kind=${opened.call.kind}#${opened.accessToken}`, "_blank", "noopener");
  }

  async function declineCallInvite() {
    if (!token) return;
    await declineWebchatCall(token).catch(() => undefined);
    setCall(null);
  }

  const lastContactRequestId = messages.reduce((current, message) => message.kind === "contact_request" ? message.id : current, 0);
  const showPhoneForm = lastContactRequestId > 0 && !(contactSent || messages.some((message) => message.kind === "contact"));
  const unavailable = config !== null && !config.available;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", width: "100%", background: "#fff", fontFamily: "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif", color: "#1f1f1f", overflow: "hidden" }}>
      <ChatHeader accent={accent} title={title} expanded={expanded} canExpand={!fullscreen} onToggleExpand={toggleExpanded} onClose={closePanel} />
      <ChatBody bodyRef={bodyRef} config={config} unavailable={unavailable} accepted={accepted} accent={accent} title={title} messages={messages} pending={pending} awaiting={awaiting || thinking} lastContactRequestId={lastContactRequestId} showPhoneForm={showPhoneForm} onSubmitContact={submitContact} audioUrlFor={token ? (id) => voiceAudioUrl(token, id) : undefined} attachmentUrlFor={token ? (id, inline) => attachmentUrl(token, id, inline) : undefined} />
      {config?.available && accepted && call && (call.status === "REQUESTED" || call.status === "RINGING") && <CallInviteBanner call={call} accent={accent} onAccept={() => void acceptCallInvite()} onDecline={() => void declineCallInvite()} />}
      {config?.available && !accepted && <StartChatFooter accent={accent} starting={starting} onAccept={() => void accept()} />}
      {config?.available && accepted && <ChatComposer accent={accent} input={input} onInput={setInput} onSend={() => void send()} voice={config.features?.voiceMessages === false ? undefined : recorder} attachment={{ file: attachment, errorText: attachmentError, pick: (file) => { if (!file) return; if (file.size > MAX_FILE_BYTES) { setAttachmentError(t("chat.file_too_big")); return; } setAttachmentError(""); setAttachment(file); }, clear: () => setAttachment(null) }} />}
      {config?.available && <BrandFooter accent={accent} />}
    </div>
  );
}
