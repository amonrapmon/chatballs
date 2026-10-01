import { useEffect, useState } from "react";
import { sendSiteFields } from "./api";
import { SiteFieldsSender } from "./siteFields";

export function useSiteFields(token: string | null, hostOrigin: string) {
  const [sender] = useState(() => new SiteFieldsSender(sendSiteFields));
  useEffect(() => { sender.setToken(token); }, [sender, token]);
  useEffect(() => {
    function receive(event: MessageEvent) {
      if (event.source !== window.parent || event.origin !== hostOrigin) return;
      if (event.data?.type === "chatballs-set-fields") sender.merge(event.data.fields);
    }
    sender.resume();
    window.addEventListener("message", receive);
    // Подписка уже установлена: лоадер может безопасно отдать накопленные поля.
    window.parent.postMessage({ type: "chatballs-fields-ready" }, hostOrigin);
    return () => {
      window.removeEventListener("message", receive);
      sender.pause();
    };
  }, [sender, hostOrigin]);
  return sender;
}
