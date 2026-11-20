import { describe, expect, it } from "vitest";

import { toSalesClient, toSalesClientRow, type ApiClient } from "./model";

const example: ApiClient = {
  id: 12,
  cid: "CUS-12",
  name: "Макс",
  phone: "",
  email: "",
  username: "",
  channels: ["MAX"],
  agents: [],
  openDialogs: 1,
  totalDialogs: 1,
  lastActivityAt: "2026-11-20T10:00:00Z",
  mode: "wait",
  lastAgentName: "",
  lastAgentCode: "",
  lastAssignee: "",
  maxIdentities: [
    { integrationId: 5, integrationName: "MAX A", externalUserId: "184842387" },
    { integrationId: 9, integrationName: "MAX B", externalUserId: "100099988" },
  ],
};

describe("contact list MAX identities", () => {
  it("preserves account-scoped IDs without changing internal contact ID", () => {
    const client = toSalesClientRow(toSalesClient(example));
    expect(client.cid).toBe("CUS-12");
    expect(client.maxIdentities).toEqual(example.maxIdentities);
    expect(client.channels[0].code).toBe("MAX");
  });

  it("allows contacts without a MAX identity", () => {
    const client = toSalesClient({ ...example, channels: ["TG"], maxIdentities: undefined });
    expect(client.maxIdentities).toEqual([]);
  });
});
