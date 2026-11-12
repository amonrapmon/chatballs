import { describe, expect, it } from "vitest";

import { toClientDetailVm, type ApiClientDetail } from "./model";

const createdAt = "2026-11-12T00:00:00Z";

function detail(): ApiClientDetail {
  return {
    id: 42,
    cid: "CUS-42",
    name: "Contact",
    email: "",
    phone: "",
    channels: ["MAX", "TG"],
    openDialogs: 0,
    totalDialogs: 3,
    firstContactAt: createdAt,
    lastActivityAt: createdAt,
    dialogs: [],
    identities: [
      { provider: "API_CONNECTOR", displayProvider: "TELEGRAM", integrationId: 101, integrationName: "TG branch A", value: "", externalUserId: "same-id", username: "first", createdAt, phoneVerifiedAt: null },
      { provider: "API_CONNECTOR", displayProvider: "TELEGRAM", integrationId: 102, integrationName: "TG branch B", value: "", externalUserId: "same-id", username: "second", createdAt, phoneVerifiedAt: null },
      { provider: "API_CONNECTOR", displayProvider: "MAX", integrationId: 103, integrationName: "MAX main", value: "", externalUserId: "same-id", username: "", createdAt, phoneVerifiedAt: null },
    ],
    activity: [],
    audit: [],
    duplicate: null,
    merges: [],
  };
}

describe("contact connection identities", () => {
  it("keeps each integration distinct even with the same external user ID", () => {
    const identities = toClientDetailVm(detail()).identities;
    expect(identities.map((item) => item.code)).toEqual(["TG", "TG", "MAX"]);
    expect(identities.map((item) => item.integrationId)).toEqual([101, 102, 103]);
    expect(identities.map((item) => item.name)).toEqual([
      "Telegram · TG branch A",
      "Telegram · TG branch B",
      "MAX · MAX main",
    ]);
    expect(identities[0].value).toBe("same-id · @first");
  });

  it("renders an unknown API Connector as generic, never WEB", () => {
    const payload = detail();
    payload.identities = [{
      provider: "API_CONNECTOR", integrationId: 104, integrationName: "Custom",
      value: "", externalUserId: "other", username: "", createdAt, phoneVerifiedAt: null,
    }];
    const [identity] = toClientDetailVm(payload).identities;
    expect(identity.code).toBe("API_CONNECTOR");
    expect(identity.integrationId).toBe(104);
  });
});
