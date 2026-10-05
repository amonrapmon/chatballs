import { describe, expect, it } from "vitest";
import type { Integration } from "../model";
import type { SiteField } from "../site-fields/model";
import { availableFields, preChatConfig, readPreChat, selectField } from "./model";

const custom: SiteField = { key: "order_number", label: "Order", type: "string", aiVisible: true, order: 0 };

describe("pre-chat settings", () => {
  it("leaves a legacy form disabled and reads the existing consent", () => {
    expect(readPreChat({ consentText: "Consent" } as Integration["config"])).toEqual({
      preChat: { enabled: false, title: "", fields: [] }, consentText: "Consent",
    });
  });

  it("selects fields once, preserves required flags, and removes unchecked fields", () => {
    const fields = [{ key: "name", required: true }];
    const selected = selectField(fields, custom.key, true);
    expect(selectField(selected, custom.key, true)).toEqual([
      { key: "name", required: true }, { key: custom.key, required: false },
    ]);
    expect(selectField(selected, "name", false)).toEqual([{ key: custom.key, required: false }]);
  });

  it("removes deleted custom fields while keeping contact and valid custom fields", () => {
    expect(availableFields([{ key: "name", required: true }, { key: "deleted", required: true }, { key: custom.key, required: false }], [custom]))
      .toEqual([{ key: "name", required: true }, { key: custom.key, required: false }]);
  });

  it("preserves other settings and leaves consent version advancement to the server", () => {
    const config = { fields: [custom], allowedOrigins: ["example.com"], title: "Widget", consentVersion: "v3", appearance: { accent: "#1677ff" } } as Integration["config"];
    const result = preChatConfig(config, {
      preChat: { enabled: true, title: " Form ", fields: [{ key: "email", required: true }, { key: "deleted", required: false }] },
      consentText: " Consent ",
    });
    expect(result).toEqual({ ...config, preChat: { enabled: true, title: "Form", fields: [{ key: "email", required: true }] }, consentText: "Consent" });
    expect(config.title).toBe("Widget");
  });
});
