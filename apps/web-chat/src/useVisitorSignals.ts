import { useEffect } from "react";
import { VisitorSignals, VISITOR_KINDS, type VisitorKind } from "./visitorSignals";

const reporter = new VisitorSignals(crypto.randomUUID());
const instanceId = new URLSearchParams(location.search).get("instanceId");

export function useVisitorSignals(token: string | null, hostOrigin: string) {
  useEffect(() => {
    const embedded = window.parent !== window;
    let suspended = false;
    const visible = () => reporter.signal(document.hidden ? "page_hidden" : "page_visible");
    const hide = () => { suspended = true; reporter.signal("page_hide"); };
    const show = () => { suspended = false; reporter.signal("page_show"); visible(); reporter.refresh(); };
    const freeze = () => { suspended = true; reporter.signal("page_freeze"); };
    const resume = () => { suspended = false; reporter.signal("page_resume"); visible(); reporter.refresh(); };
    const offline = () => reporter.signal("connection_lost");
    const online = () => { visible(); reporter.refresh(); };
    function receive(event: MessageEvent) {
      if (!embedded || event.source !== window.parent || event.origin !== hostOrigin) return;
      if (event.data?.type !== "chatballs-visitor-signal" || event.data.instanceId !== instanceId) return;
      const kind = event.data.kind as VisitorKind;
      if (VISITOR_KINDS.includes(kind) && kind !== "heartbeat" && kind !== "connection_lost") reporter.signal(kind);
    }
    visible();
    if (!embedded) reporter.signal("widget_open");
    window.addEventListener("message", receive);
    window.addEventListener("pagehide", hide);
    window.addEventListener("pageshow", show);
    window.addEventListener("offline", offline);
    window.addEventListener("online", online);
    document.addEventListener("visibilitychange", visible);
    document.addEventListener("freeze", freeze);
    document.addEventListener("resume", resume);
    reporter.setToken(token);
    if (embedded) window.parent.postMessage({ type: "chatballs-visitor-ready", instanceId }, hostOrigin);
    const timer = window.setInterval(() => { if (!suspended && navigator.onLine) reporter.refresh(); }, 30_000);
    return () => {
      clearInterval(timer);
      window.removeEventListener("message", receive);
      window.removeEventListener("pagehide", hide);
      window.removeEventListener("pageshow", show);
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
      document.removeEventListener("visibilitychange", visible);
      document.removeEventListener("freeze", freeze);
      document.removeEventListener("resume", resume);
      // Effect replay must not reset the same document's sequence.
    };
  }, [token, hostOrigin]);
}
