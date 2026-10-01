import { describe, expect, it } from "vitest";
import { formPayload, inputValue, preChatFields, validField, type PreChatField } from "./preChatModel";
import { formatPhone } from "./phoneFormat";
import { consentMatches } from "./useWidgetConsent";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PreChatField as FieldControl } from "./PreChatField";

function field(type: PreChatField["type"], required = true): PreChatField {
  return { key: "value", label: "Value", type, required };
}

describe("pre-chat validation and session consent", () => {
  it("renders a switch, enum choices and a native date/time control", () => {
    const render = (definition: PreChatField, value: string | boolean) => renderToStaticMarkup(createElement(FieldControl, {
      field: definition, value, fromSite: false, onChange: () => {},
    }));
    expect(render(field("boolean"), false)).toContain('role="switch"');
    const select = render({ ...field("enum"), options: [{ value: "new", label: "New" }] }, "new");
    expect(select).toContain("<select");
    expect(select).toContain('value="new" selected=""');
    expect(render(field("datetime"), "2026-10-01T12:30")).toContain('type="datetime-local"');
  });
  it("uses configured order, required flags and custom schema labels", () => {
    expect(preChatFields({ available: true, fields: [{ key: "order", label: "Order", type: "number" }],
      preChat: { enabled: true, title: "", fields: [{ key: "order", required: false }, { key: "email", required: true }] },
    }).map(({ key, label, type, required }) => ({ key, label, type, required }))).toEqual([
      { key: "order", label: "Order", type: "number", required: false },
      { key: "email", label: "Email", type: "email", required: true },
    ]);
  });

  it("blocks missing required values and invalid optional email and phone", () => {
    expect(validField(field("string"), "  ")).toBe(false);
    expect(validField(field("email", false), "")).toBe(true);
    expect(validField(field("email", false), "client@")).toBe(false);
    expect(validField(field("email", false), "client..name@example.test")).toBe(false);
    expect(validField(field("email", false), "client@-example.test")).toBe(false);
    expect(validField(field("email"), "client@example.test")).toBe(true);
    expect(validField(field("phone", false), formatPhone("8999"))).toBe(false);
    expect(validField(field("phone"), formatPhone("89991234567"))).toBe(true);
    expect(inputValue(field("phone"), "89991234567")).toBe("+7 (999) 123-45-67");
  });

  it("treats false and zero as values, checks enum membership and typed values", () => {
    expect(validField(field("boolean"), false)).toBe(true);
    expect(validField(field("boolean"), "")).toBe(false);
    expect(validField(field("number"), "0")).toBe(true);
    expect(validField(field("number"), "abc")).toBe(false);
    expect(validField({ ...field("enum"), options: [{ value: "new", label: "New" }] }, "old")).toBe(false);
    expect(validField(field("datetime"), "not-a-date")).toBe(false);
    expect(validField(field("datetime"), "2026-10-01T12:30")).toBe(true);
    expect(validField(field("url"), "javascript:alert(1)")).toBe(false);
  });

  it("sends typed values and explicit clears overriding site values", () => {
    const fields = [field("string", false), { ...field("boolean"), key: "flag" }, { ...field("number"), key: "count" }];
    expect(formPayload(fields, { value: "  ", flag: false, count: "0" })).toEqual({ value: null, flag: false, count: 0 });
  });

  it("requires both a session and consent to the current version", () => {
    expect(consentMatches("session", "v3", "v3")).toBe(true);
    expect(consentMatches("session", "v2", "v3")).toBe(false);
    expect(consentMatches("session", null, "v3")).toBe(false);
    expect(consentMatches(null, "v3", "v3")).toBe(false);
    expect(consentMatches("session", "v3", undefined)).toBe(false);
  });
});
