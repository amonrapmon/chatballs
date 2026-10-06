import { describe, expect, it } from "vitest";
import { serverDraft, sourceFromKey, sourceKey, duplicateParameter, moveParameter } from "./model";
import { draftErrors, mergeErrors, parameterError } from "./validation";
import type { ParameterSource, ToolParameter } from "./types";
import type { Integration } from "../model";

const order: ToolParameter = { name: "order_number", type: "string", required: true, location: "path", description: "",
  source: { type: "web_field", integrationId: 22, key: "order_number" } };

describe("external server editor", () => {
  it("keeps refreshed tool snapshots out of editable settings and retains masked headers", () => {
    const integration = { name: "CRM", isActive: true, externalServer: {
      type: "mcp", url: "https://example.com/mcp", description: "Orders",
      headers: [{ name: "Authorization", value: "", secret: true }], tools: [], toolsState: "loaded",
      toolsRefreshedAt: "2026-10-05T09:00:00Z",
    } } as unknown as Integration;
    const draft = serverDraft("mcp", integration);
    expect(draft.externalServer.headers).toEqual([{ name: "Authorization", value: "", secret: true, saved: true }]);
    integration.externalServer!.toolsState = "unreachable";
    integration.externalServer!.toolsRefreshedAt = "2026-10-05T10:00:00Z";
    expect(serverDraft("mcp", integration)).toEqual(draft);
    expect(draft.externalServer).not.toHaveProperty("tools");
  });

  it("keeps every client binding distinct when switching sources", () => {
    const sources: ParameterSource[] = [{ type: "ai" }, { type: "contact", field: "email" }, order.source,
      { type: "web_field", integrationId: 7, key: "order_number" }];
    expect(new Set(sources.map(sourceKey)).size).toBe(sources.length);
    for (const source of sources) expect(sourceFromKey(sourceKey(source))).toEqual(source);
  });

  it("collects name, description and unresolved URL placeholder errors together", () => {
    const draft = serverDraft("http");
    draft.name = "Статус заказа";
    draft.externalServer = { ...draft.externalServer, toolName: "get order", url: "https://example.com/orders/{missing}", parameters: [order] };
    expect(Object.keys(draftErrors(draft)).sort()).toEqual(["description", "parameters", "toolName", "url"]);
    draft.externalServer.toolName = "get_order_status";
    draft.externalServer.description = "Order status";
    draft.externalServer.url = "https://example.com/orders/{order_number}";
    expect(draftErrors(draft)).toEqual({});
  });

  it("prevents duplicate names and GET body parameters", () => {
    expect(parameterError(order, [order, order], 1, "https://example.com/{order_number}", "GET")).not.toBe("");
    expect(parameterError({ ...order, location: "body" }, [], 0, "https://example.com", "GET")).not.toBe("");
    expect(parameterError({ ...order, location: "body" }, [], 0, "https://example.com", "POST")).toBe("");
  });

  it("duplicates a path parameter without a second path placeholder and preserves its source", () => {
    const next = duplicateParameter([order, { ...order, name: "order_number_2", location: "query" }], 0);
    expect(next[1]).toEqual({ ...order, name: "order_number_3", location: "query" });
    expect(next[1].source).not.toBe(order.source);
    expect(moveParameter(next, 1, -1).map((p) => p.name)).toEqual(["order_number_3", "order_number", "order_number_2"]);
  });

  it("retains network errors beside unresolved placeholders without double counting", () => {
    expect(mergeErrors({ url: ["private address"] }, { url: ["unknown placeholder"] }, { url: ["private address"] }))
      .toEqual({ url: ["private address", "unknown placeholder"] });
  });

  it("treats URL substitutions as required path parameters when switching from POST to GET", () => {
    expect(parameterError({ ...order, location: "body" }, [order], 0, "https://example.com/{order_number}", "GET")).toBe("");
  });
});
