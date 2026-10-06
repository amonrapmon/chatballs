import { describe, expect, it } from "vitest";
import { ApiError } from "../../../api/client";
import { t } from "../../../i18n";
import { aiAccessFor, fieldError, fieldsSaveError, fieldsSnippet, moveField, optionError, type SiteField } from "./model";

const customer: SiteField = { id: "server-id", key: "user_id", label: "ID", type: "string", aiAccess: "hidden", order: 0 };
const status: SiteField = { key: "order_status", label: "Status", type: "enum", aiAccess: "open", order: 1,
  options: [{ label: "Cooking", value: "cooking" }, { label: "On the way", value: "on_the_way" }] };

describe("website field schema editor", () => {
  it("rejects reserved, malformed and duplicate keys and the field limit", () => {
    for (const key of ["name", "email", "phone"]) {
      expect(fieldError({ ...customer, key }, [], true)).toBe(t("site_fields.key_reserved"));
    }
    for (const key of ["Upper", "1field", "a-b", "a".repeat(41)]) {
      expect(fieldError({ ...customer, key }, [], true)).toBe(t("site_fields.key_invalid"));
    }
    expect(fieldError(customer, [customer], true)).toBe(t("site_fields.key_duplicate"));
    expect(fieldError(customer, Array.from({ length: 30 }, () => customer), true)).toBe(t("site_fields.limit"));
    expect(fieldError({ ...customer, label: "a".repeat(61) }, [], false)).toBe(t("site_fields.label_invalid"));
  });

  it("reorders without losing immutable server ids, options or AI access", () => {
    const moved = moveField([customer, status], "order_status", "user_id");
    expect(moved).toEqual([{ ...status, order: 0 }, { ...customer, order: 1 }]);
    expect(moveField(moved, "missing", "user_id")).toBe(moved);
  });

  it("never leaves an email or a phone open to AI when the type changes", () => {
    expect(aiAccessFor("email", "open")).toBe("masked");
    expect(aiAccessFor("phone", "open")).toBe("masked");
    expect(aiAccessFor("phone", "hidden")).toBe("hidden");
    expect(aiAccessFor("string", "open")).toBe("open");
  });

  it("validates unique list values and six-digit colors while allowing an existing value to be edited", () => {
    const option = { label: "Cooking", value: "cooking", color: "#faad14" };
    expect(optionError(option, [option])).toBe(t("site_fields.option_duplicate"));
    expect(optionError(option, [option], 0)).toBeUndefined();
    expect(optionError({ ...option, color: "red" }, [])).toBe(t("site_fields.option_invalid"));
  });

  it("generates executable partial updates from the current schema, escaping values", () => {
    const fields = [customer, { ...status, key: "quoted_status", options: [{ label: "Quoted", value: 'a"b' }, status.options![1]] }];
    const calls: Record<string, unknown>[] = [];
    new Function("Chatballs", fieldsSnippet(fields))({ setFields: (values: Record<string, unknown>) => calls.push(values) });
    expect(calls[0]).toMatchObject({ user_id: "u_58213", quoted_status: 'a"b' });
    expect(calls[1]).toEqual({ quoted_status: "on_the_way" });
    expect(fieldsSnippet([customer])).not.toContain("order_status");
    const example = fieldsSnippet([{ ...status, options: [{ label: "Accepted", value: "accepted" }, ...status.options!] }]);
    expect(example).toContain('order_status: "cooking"');
    expect(example).toContain('Chatballs.setFields({ order_status: "on_the_way" });');
  });

  it("keeps user-facing server validation messages and hides technical runtime failures", () => {
    const detail = "Своих полей может быть не больше 30 — удалите лишние";
    expect(fieldsSaveError(new ApiError(400, { detail }))).toBe(detail);
    expect(fieldsSaveError(new Error("Organization context is required"))).toBe(t("common.could_not_save"));
    expect(fieldsSaveError(new ApiError(500, { detail: "Database failure" }))).toBe(t("common.could_not_save"));
  });
});
