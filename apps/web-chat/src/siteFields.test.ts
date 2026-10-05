import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SiteFields } from "./api";
import { SiteFieldsSender } from "./siteFields";

describe("site fields delivery", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  function setup(sendResult: () => Promise<boolean> = async () => true) {
    const calls: { token: string; fields: SiteFields; time: number }[] = [];
    const sender = new SiteFieldsSender(async (token, fields) => {
      calls.push({ token, fields, time: Date.now() });
      return sendResult();
    });
    sender.resume();
    return { sender, calls };
  }

  it("merges in memory before start and sends changes arriving during start", async () => {
    const { sender, calls } = setup();
    sender.merge({ name: "Иван", status: "cooking" });
    sender.merge({ status: null, amount: 0, has_order: false });
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls).toEqual([]);
    let resolve!: (token: string) => void;
    let initial: SiteFields = {};
    const start = sender.start((fields) => {
      initial = fields;
      return new Promise<string>((done) => { resolve = done; });
    });
    expect(initial).toEqual({ name: "Иван", status: null, amount: 0, has_order: false });
    sender.merge({ status: "delivered" });
    resolve("session");
    expect(await start).toBe("session");
    await vi.advanceTimersByTimeAsync(499);
    expect(calls).toEqual([]);
    await vi.advanceTimersByTimeAsync(1);
    expect(calls[0]).toMatchObject({ token: "session", fields: { status: "delivered" } });
  });

  it("publishes site values before a session without sending them", async () => {
    const { sender, calls } = setup();
    const initial = sender.getSnapshot();
    let updates = 0;
    const unsubscribe = sender.subscribe(() => { updates += 1; });
    sender.merge({ name: "Иван", confirmed: false });
    sender.merge({ name: "Иван" });
    expect(sender.getSnapshot()).toEqual({ name: "Иван", confirmed: false });
    expect(initial).toEqual({});
    expect(updates).toBe(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls).toEqual([]);
    unsubscribe();
  });

  it("coalesces updates and sends at most once every 500 ms without overlapping", async () => {
    let finish!: (ok: boolean) => void;
    const { sender, calls } = setup(() => new Promise<boolean>((done) => { finish = done; }));
    sender.setToken("restored");
    sender.merge({ status: "cooking" });
    sender.merge({ status: "on_the_way", name: "Иван" });
    await vi.advanceTimersByTimeAsync(500);
    expect(calls[0].fields).toEqual({ status: "on_the_way", name: "Иван" });
    sender.merge({ status: null });
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls).toHaveLength(1);
    finish(true);
    await vi.advanceTimersByTimeAsync(500);
    expect(calls[1].fields).toEqual({ status: null });
    expect(calls[1].time - calls[0].time).toBeGreaterThanOrEqual(500);
    finish(true);
  });

  it.each(["rejection", "http failure"])("retains latest fields after %s and retries", async (failure) => {
    let attempts = 0;
    const { sender, calls } = setup(async () => {
      if (++attempts === 1) {
        if (failure === "rejection") throw new Error("offline");
        return false;
      }
      return true;
    });
    sender.setToken("session");
    sender.merge({ status: "cooking", name: "Иван" });
    await vi.advanceTimersByTimeAsync(500);
    sender.merge({ status: "delivered" });
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls[1].fields).toEqual({ status: "delivered", name: "Иван" });
    sender.merge({ status: "delivered" });
    await vi.advanceTimersByTimeAsync(500);
    expect(calls).toHaveLength(2);
  });

  it("keeps fields after failed start and replays them for a new session", async () => {
    const { sender } = setup();
    sender.merge({ name: "Иван" });
    const starts: number[] = [];
    expect(await sender.start(async () => { starts.push(Date.now()); throw new Error("offline"); })).toBeNull();
    const retry = sender.start(async (fields) => {
      starts.push(Date.now());
      expect(fields).toEqual({ name: "Иван" });
      return "session";
    });
    await vi.advanceTimersByTimeAsync(499);
    expect(starts).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(await retry).toBe("session");
    expect(starts[1] - starts[0]).toBe(500);
    sender.setToken(null);
    const restart = sender.start(async (fields) => {
      expect(fields).toEqual({ name: "Иван" });
      return "new-session";
    });
    await vi.advanceTimersByTimeAsync(500);
    await restart;
  });

  it("ignores malformed fields and cancels delivery on unmount", async () => {
    const { sender, calls } = setup();
    sender.setToken("session");
    sender.merge(null);
    sender.merge([]);
    sender.merge({ invalid: {}, amount: Infinity, constructor: "value", name: "Иван" });
    sender.pause();
    await vi.advanceTimersByTimeAsync(1000);
    expect(calls).toEqual([]);
    sender.resume();
    await vi.advanceTimersByTimeAsync(500);
    expect(calls[0].fields).toEqual({ constructor: "value", name: "Иван" });
  });
});
