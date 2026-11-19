import { useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { setActiveOrganization } from "../../api/client";
import type { Integration } from "./model";
import { useIntegrationForm } from "./useIntegrationForm";

const organizationId = "12345678-1234-1234-1234-123456789abc";
const collection = `/api/v1/organizations/${organizationId}/integrations/`;
const fetchIntegration = vi.fn<typeof fetch>();

beforeEach(() => {
  setActiveOrganization(organizationId);
  fetchIntegration.mockReset().mockImplementation(async () => Response.json({ integration: { id: 42 } }));
  vi.stubGlobal("document", { cookie: "" });
  vi.stubGlobal("fetch", fetchIntegration);
});

afterEach(() => {
  vi.unstubAllGlobals();
  setActiveOrganization(null);
});

async function save(initial: Integration | null) {
  let submit: (() => Promise<void>) | undefined;
  const onSaved = vi.fn();
  function Harness() {
    const [initialized, setInitialized] = useState(false);
    const form = useIntegrationForm({ initial, kind: "MESSENGER", allowedProviders: initial?.provider === "VK" ? ["VK"] : ["API_CONNECTOR", "GATEWAY"], onSaved });
    if (!initial && !initialized) {
      form.setName("Support");
      form.setConnectorService("custom_adapter");
      setInitialized(true);
    }
    submit = form.submit;
    return null;
  }
  renderToStaticMarkup(<Harness />);
  await submit?.();
  expect(onSaved).toHaveBeenCalledOnce();
  const [path, init] = fetchIntegration.mock.calls[0];
  return { path, method: init?.method, body: JSON.parse(String(init?.body)) };
}

it("creates a Connector with both settings off by default", async () => {
  expect(await save(null)).toMatchObject({
    path: collection, method: "POST", body: {
      provider: "API_CONNECTOR", config: {
        connectorService: "custom_adapter", mirrorExternalOutgoingEnabled: false, connectorAiOutboundEnabled: false,
      },
    },
  });
});

it.each([[true, false], [false, true]])("preserves saved mirroring=%s and AI outbound=%s independently", async (mirror, aiOutbound) => {
  const initial: Integration = {
    id: 42, kind: "MESSENGER", provider: "API_CONNECTOR", name: "Support", hasSecret: true, secretMasked: "",
    isActive: true, channel: null, status: "UNCHECKED", lastCheckedAt: null, lastError: "", createdAt: "", updatedAt: "",
    config: {
      connectorService: "custom_adapter", mirrorExternalOutgoingEnabled: mirror, connectorAiOutboundEnabled: aiOutbound,
    } as Integration["config"],
  };
  expect(await save(initial)).toMatchObject({
    path: `${collection}42/`, method: "PATCH", body: { config: {
      connectorService: "custom_adapter", mirrorExternalOutgoingEnabled: mirror, connectorAiOutboundEnabled: aiOutbound,
    } },
  });
});

it("updates an existing Gateway with its original config and channel", async () => {
  const initial: Integration = {
    id: 42, kind: "MESSENGER", provider: "GATEWAY", name: "Existing Gateway", hasSecret: true, secretMasked: "",
    isActive: true, channel: { id: 7, code: "support", name: "Support", hasAgent: true },
    status: "OK", lastCheckedAt: null, lastError: "", createdAt: "", updatedAt: "",
    config: { sourceId: "legacy-7", baseUrl: "https://gateway.example/" } as Integration["config"],
  };
  expect(await save(initial)).toEqual({
    path: `${collection}42/`, method: "PATCH", body: {
      name: "Existing Gateway", channelId: 7, config: { sourceId: "legacy-7", baseUrl: "https://gateway.example/" },
    },
  });
});

it.each([true, false])("round-trips VK native mirror enabled=%s in the connection form", async enabled => {
  const initial: Integration = {
    id: 42, kind: "MESSENGER", provider: "VK", name: "VK community", hasSecret: true, secretMasked: "",
    isActive: true, channel: { id: 7, code: "vk", name: "VK" },
    status: "OK", lastCheckedAt: null, lastError: "", createdAt: "", updatedAt: "",
    config: {
      baseUrl: "https://api.vk.com/method", nativeMirrorEnabled: enabled,
    } as Integration["config"],
  };
  expect(await save(initial)).toMatchObject({
    path: `${collection}42/`, method: "PATCH",
    body: { config: { nativeMirrorEnabled: enabled }, channelId: 7 },
  });
});
