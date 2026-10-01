import type { SiteField } from "@chatballs/contracts";
import { useEffect, useState } from "react";

import { nextSiteFieldExpiry } from "./siteData";

const EMPTY_FIELDS: SiteField[] = [];

export function subscribeSiteDataClock(fields: SiteField[], onTick: (now: number) => void): () => void {
  let timer: number | undefined;
  function tick() {
    const current = Date.now();
    onTick(current);
    const expiry = nextSiteFieldExpiry(fields, current);
    if (expiry !== undefined) timer = window.setTimeout(tick, expiry - current);
  }
  tick();
  return () => window.clearTimeout(timer);
}

export function useSiteDataClock(fields: SiteField[] = EMPTY_FIELDS): number {
  const [now, setNow] = useState(Date.now);
  useEffect(() => subscribeSiteDataClock(fields, setNow), [fields]);
  return now;
}
