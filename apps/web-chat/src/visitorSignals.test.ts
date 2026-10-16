import { describe, expect, it } from "vitest";
import { VisitorSignals, type VisitorSignal } from "./visitorSignals";

describe("visitor signal ordering", () => {
  it("serializes axes independently and preserves sequence on returning to the same session", async () => {
    const events: VisitorSignal[] = [];
    const reporter = new VisitorSignals("tab-a", async (_token, signal) => { events.push(signal); });
    reporter.signal("widget_close");
    reporter.setToken("session-a");
    reporter.signal("page_hide");
    reporter.signal("connection_lost");
    await reporter.settled();
    expect(events.map((event) => event.kind)).toEqual(["widget_close", "page_visible", "heartbeat", "page_hide", "connection_lost"]);
    expect(events.map((event) => event.sequence)).toEqual([1, 2, 3, 4, 5]);
    reporter.setToken(null); reporter.setToken("session-a"); await reporter.settled();
    expect(events.at(-1)?.sequence).toBe(8);
    reporter.setToken("session-b"); await reporter.settled();
    expect(events.at(-1)?.sequence).toBe(3);
  });
  it("collects no authenticated signals before consent and recovers after a failed request", async () => {
    const events: VisitorSignal[] = [];
    let fail = true;
    const reporter = new VisitorSignals("tab-b", async (_token, signal) => {
      if (fail) { fail = false; throw new Error("offline"); }
      events.push(signal);
    });
    reporter.signal("page_hidden"); await reporter.settled(); expect(events).toEqual([]);
    reporter.setToken("session"); reporter.signal("widget_open"); await reporter.settled();
    expect(events.map((event) => event.sequence)).toEqual([2, 3]);
    expect(events.at(-1)?.tabId).toBe("tab-b");
  });
});
