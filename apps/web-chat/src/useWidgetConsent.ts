import { useState } from "react";
import { poll, sendSiteFields, SessionExpired, startSession, type SiteFields, type WebConfig, type WidgetEntry } from "./api";
import { useSiteFields } from "./useSiteFields";

export function consentMatches(token: string | null, saved: string | null, current: string | undefined): boolean {
  return Boolean(token && current && saved === current);
}

export function useWidgetConsent(config: WebConfig | null, entry: WidgetEntry, hostOrigin: string, tokenKey: string) {
  const versionKey = `${tokenKey}:consent-version`;
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(tokenKey));
  const [version, setVersion] = useState<string | null>(() => localStorage.getItem(versionKey));
  const [starting, setStarting] = useState(false);
  const accepted = consentMatches(token, version, config?.consent?.version);
  const siteFields = useSiteFields(accepted ? token : null, hostOrigin);

  function forgetConsent() {
    localStorage.removeItem(tokenKey);
    localStorage.removeItem(versionKey);
    setToken(null);
    setVersion(null);
  }

  async function accept(preChatFields?: SiteFields) {
    if (starting || !config?.available) return;
    setStarting(true);
    try {
      const nextToken = await siteFields.start(async (fields) => {
        if (token) {
          try {
            await poll(token, 0);
            return await sendSiteFields(token, { ...fields, ...preChatFields }) ? token : null;
          } catch (error) {
            if (!(error instanceof SessionExpired)) return null;
          }
        }
        return startSession(entry, hostOrigin, fields, preChatFields, config.consent?.version);
      });
      if (!nextToken) return;
      const nextVersion = config.consent?.version ?? "";
      localStorage.setItem(tokenKey, nextToken);
      localStorage.setItem(versionKey, nextVersion);
      setToken(nextToken);
      setVersion(nextVersion);
    } finally { setStarting(false); }
  }

  return { token, accepted, starting, accept, forgetConsent, siteValues: siteFields.values };
}
