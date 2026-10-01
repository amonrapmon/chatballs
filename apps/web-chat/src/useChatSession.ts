import { useEffect, useRef, useState } from "react";

import {
  declineWebchatCall,
  getConfig,
  openWebchatCall,
  poll,
  sendContact,
  sendMessage,
  sendFile,
  sendVoice,
  type CallInfo,
  type Poll,
  type WebConfig,
  type WebMessage,
} from "./api";
import { useScrollToLatest } from "./useScrollToLatest";
import { useWidgetConsent } from "./useWidgetConsent";
import { useChatPolling } from "./useChatPolling";
import { useVoiceRecorder } from "./useVoiceRecorder";
import { useWidgetActivity } from "./widgetActivity";
import { applyWidgetLanguage, t } from "./i18n";

const PARAMS = new URLSearchParams(location.search);
const WIDGET_KEY = PARAMS.get("widgetKey") || "";
const LEGACY_CHANNEL = PARAMS.get("channel") || "";
const ENTRY = WIDGET_KEY ? { widgetKey: WIDGET_KEY } : { channel: LEGACY_CHANNEL };
const HOST_ORIGIN = document.referrer ? new URL(document.referrer).origin : location.origin;
const TOKEN_KEY = `chatballs-chat-token:${WIDGET_KEY || `channel:${LEGACY_CHANNEL}`}`;

export function useChatSession() {
  const [config, setConfig] = useState<WebConfig | null>(null);
  const { token, accepted, starting, accept, forgetConsent, siteValues } = useWidgetConsent(config, ENTRY, HOST_ORIGIN, TOKEN_KEY);
  const [messages, setMessages] = useState<WebMessage[]>([]);
  const [pending, setPending] = useState<string[]>([]);
  const [state, setState] = useState<"ai" | "operator" | "waiting">("ai");
  const [awaiting, setAwaiting] = useState(false);
  // Ответ считается на сервере и приедет следующим опросом: до тех пор в ленте
  // висит «печатает».
  const [thinking, setThinking] = useState(false);
  const [input, setInput] = useState("");
  const [contactSent, setContactSent] = useState(false);
  const [attachment, setAttachment] = useState<File | null>(null);
  const [attachmentError, setAttachmentError] = useState("");
  const [call, setCall] = useState<CallInfo | null>(null);
  const lastId = useRef(0);
  const openedCallId = useRef("");
  const pollingReady = useRef(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const scrollToLatest = useScrollToLatest(bodyRef);
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

  useChatPolling(accepted ? token : null, lastId, pollingReady, ingestPoll, forgetSession);

  useEffect(() => {
    scrollToLatest();
  }, [scrollToLatest, messages, pending, awaiting]);

  function forgetSession() {
    forgetConsent();
    lastId.current = 0;
    pollingReady.current = false;
    setMessages([]);
    setPending([]);
    setAwaiting(false);
    setThinking(false);
    setCall(null);
    setContactSent(false);
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

  return { config, accepted, siteValues, messages, pending, awaiting, thinking, call, input, setInput, starting, recorder, bodyRef, token, lastContactRequestId, showPhoneForm, unavailable, accept, send, submitContact, acceptCallInvite, declineCallInvite, attachment, attachmentError, setAttachment, setAttachmentError };
}
