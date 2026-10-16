export const VISITOR_KINDS = ["widget_open", "widget_close", "page_visible", "page_hidden", "page_freeze", "page_resume", "page_hide", "page_show", "heartbeat", "connection_lost"] as const;
export type VisitorKind = typeof VISITOR_KINDS[number];
export type VisitorSignal = { tabId: string; sequence: number; kind: VisitorKind };

export async function postVisitorSignal(token: string, signal: VisitorSignal) {
  const response = await fetch("/api/v1/webchat/observations/", {
    method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(signal), keepalive: true, signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error(String(response.status));
}

// One identity per iframe document, preserved by BFCache; never stored in
// localStorage/sessionStorage (duplicated tabs must not share it).
export class VisitorSignals {
  private token: string | null = null;
  private sequence = 0;
  private tail = Promise.resolve();
  private widget: VisitorKind | null = null;
  private sequences = new Map<string, number>();
  private page: VisitorKind = "page_visible";
  constructor(readonly tabId: string, private post = postVisitorSignal) {}

  setToken(token: string | null) {
    if (token === this.token) return;
    this.token = token;
    this.sequence = token ? this.sequences.get(token) ?? 0 : 0;
    if (token) this.refresh();
  }

  signal(kind: VisitorKind) {
    if (kind.startsWith("widget_")) this.widget = kind;
    if (kind.startsWith("page_")) this.page = kind;
    const token = this.token;
    if (!token) return;
    const signal = { tabId: this.tabId, sequence: ++this.sequence, kind };
    this.sequences.set(token, this.sequence);
    // The server orders all axes by one sequence; serialize requests so a
    // heartbeat cannot arrive before an earlier close/lifecycle observation.
    this.tail = this.tail.then(async () => {
      if (this.token === token) await this.post(token, signal);
    }).catch(() => undefined);
  }

  refresh() {
    if (this.widget) this.signal(this.widget);
    this.signal(this.page);
    this.signal("heartbeat");
  }

  settled() { return this.tail; }
}
