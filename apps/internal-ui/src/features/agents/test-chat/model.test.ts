import { describe, expect, it } from "vitest";
import { chatHistory, clientData, dataSummary, displayReply, testConnections, validClientData, type TestConnection, type TestValues } from "./model";
import type { Integration } from "../../integrations/model";

const connections: TestConnection[] = [
  { id: 42, name: "Main", fields: [
    { key: "order", label: "Order", type: "number" },
    { key: "member", label: "Member", type: "boolean" },
    { key: "state", label: "State", type: "enum", options: [{ value: "ready", label: "Ready" }] },
    { key: "date", label: "Date", type: "datetime" },
    { key: "url", label: "URL", type: "url" },
  ] },
  { id: 43, name: "Second", fields: [{ key: "order", label: "Order", type: "string" }] },
];

describe("agent test client data", () => {
  it("keeps connection namespaces, false and zero, and sends a reset as an empty object", () => {
    expect(clientData({ name: " Anna ", "42:order": "0", "42:member": false, "43:order": "A-2291" }, connections)).toEqual({
      name: "Anna", webFields: { "42": { order: 0, member: false }, "43": { order: "A-2291" } },
    });
    expect(clientData({}, connections)).toEqual({});
    expect(clientData({ email: " ", "42:order": "" }, connections)).toEqual({});
  });

  it("allows missing values, checks typed values and enum membership", () => {
    expect(validClientData({}, connections)).toBe(true);
    expect(validClientData({ email: "anna@example.test", phone: "+7 (999) 123-45-67", "42:member": false,
      "42:order": "0", "42:state": "ready", "42:date": "2026-10-05T12:30", "42:url": "https://example.test" }, connections)).toBe(true);
    const invalid: TestValues[] = [{ email: "anna@" }, { phone: "123" }, { "42:order": "abc" }, { "42:state": "unknown" },
      { "42:date": "bad" }, { "42:url": "javascript:alert(1)" }];
    for (const values of invalid) expect(validClientData(values, connections)).toBe(false);
  });

  it("reads every schema field only from this agent's web connections, in schema order", () => {
    const item = { id: 42, name: "Main", provider: "WEB", channel: { id: 7 }, config: { fields: [
      { key: "second", label: "Second", type: "string", order: 1 },
      { key: "first", label: "First", type: "boolean", order: 0 },
    ] } } as Integration;
    const result = testConnections([item, { ...item, id: 43, channel: { ...item.channel!, id: 8 } },
      { ...item, id: 44, provider: "EMAIL" }], 7);
    expect(result).toHaveLength(1);
    expect(result[0].fields.map((field) => field.key)).toEqual(["first", "second"]);
  });

  it("passes completed conversation history without tool metadata or failed turns", () => {
    const calls = [{ tool: "Orders", ok: true, durationMs: 400, error: "" }];
    expect(chatHistory([{ message: "Hello", reply: "Hi", calls, createdAt: "now" },
      { message: "Again", error: "Failed", calls, createdAt: "now" }])).toEqual([
      { role: "user", content: "Hello" }, { role: "assistant", content: "Hi" },
    ]);
  });

  it("shows enum labels in the collapsed summary instead of API values", () => {
    expect(dataSummary({ "42:state": "ready", "42:member": false }, connections)).toBe("Ready · ещё 1 поле");
  });

  it("removes the internal handoff marker from the visible reply and history", () => {
    expect(displayReply("A colleague will help.\n<<HANDOFF>>")).toBe("A colleague will help.");
  });
});
