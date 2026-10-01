import type { SiteFields } from "./api";

const INTERVAL_MS = 500;

/** Поля живут в памяти; запросы сериализованы, включая старт сессии. */
export class SiteFieldsSender {
  private values: SiteFields = {};
  private pending: SiteFields = {};
  private token: string | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private busy = false;
  private active = false;
  private lastSent = -Infinity;
  private retryDelay = INTERVAL_MS;

  constructor(private readonly send: (token: string, fields: SiteFields) => Promise<boolean>) {}

  resume() { this.active = true; this.schedule(); }
  pause() { this.active = false; clearTimeout(this.timer); this.timer = undefined; }

  setToken(token: string | null) {
    if (this.token === token) return;
    this.token = token;
    if (!token) this.pending = { ...this.values };
    this.schedule();
  }

  merge(fields: unknown) {
    if (!fields || typeof fields !== "object" || Array.isArray(fields)) return;
    for (const [key, value] of Object.entries(fields)) {
      if (!/^[a-z][a-z0-9_]{0,39}$/.test(key)) continue;
      if (value !== null && typeof value !== "string" && typeof value !== "boolean"
        && (typeof value !== "number" || !Number.isFinite(value))) continue;
      if (Object.hasOwn(this.values, key) && this.values[key] === value) continue;
      this.values[key] = value;
      this.pending[key] = value;
    }
    this.schedule();
  }

  async start(issue: (fields: SiteFields) => Promise<string | null>): Promise<string | null> {
    if (this.busy) return null;
    this.busy = true;
    const wait = this.lastSent + INTERVAL_MS - Date.now();
    if (wait > 0) await new Promise<void>((resolve) => setTimeout(resolve, wait));
    const fields = { ...this.values };
    this.pending = {};
    this.lastSent = Date.now();
    try {
      const token = await issue(fields);
      if (token) this.token = token;
      else this.pending = { ...fields, ...this.pending };
      return token;
    } catch {
      this.pending = { ...fields, ...this.pending };
      return null;
    } finally {
      this.busy = false;
      this.schedule();
    }
  }

  private schedule(delay = INTERVAL_MS) {
    if (!this.active || !this.token || this.busy || this.timer !== undefined
      || !Object.keys(this.pending).length) return;
    const wait = Math.max(delay, this.lastSent + INTERVAL_MS - Date.now());
    this.timer = setTimeout(() => { this.timer = undefined; void this.flush(); }, wait);
  }

  private async flush() {
    if (!this.active || !this.token || this.busy) return;
    const token = this.token;
    const fields = this.pending;
    this.pending = {};
    this.busy = true;
    this.lastSent = Date.now();
    let ok = false;
    try { ok = await this.send(token, fields); } catch { /* сеть не влияет на чат */ }
    if (!ok && this.token === token) {
      this.pending = { ...fields, ...this.pending };
      this.retryDelay = Math.min(this.retryDelay * 2, 30_000);
    } else this.retryDelay = INTERVAL_MS;
    this.busy = false;
    this.schedule(this.retryDelay);
  }
}
