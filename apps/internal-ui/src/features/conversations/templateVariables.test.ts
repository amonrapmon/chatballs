import { describe, expect, it } from "vitest";

import { unfilledVariables } from "./templateVariables";

describe("переменные шаблона ответа", () => {
  it("находит незаполненные переменные без повторов", () => {
    expect(unfilledVariables("{{client_name}}, {{client_name}} и {{company}}, {{unknown}}")).toEqual(["client_name", "company"]);
    expect(unfilledVariables("Готовый текст")).toEqual([]);
  });

  it("blocks standard and deleted custom fields in final text and captions", () => {
    expect(unfilledVariables("{{ contact.email }} {{contact.fields.12.removed_field}} {{contact.email}} {{unknown}}"))
      .toEqual(["contact.email", "contact.fields.12.removed_field"]);
    expect(unfilledVariables("{{contact.fields.0.invalid}} {{contact.fields.12.invalid-key}} {company}"))
      .toEqual([]);
  });

  it("retains server-reported unresolved keys until they are edited out", () => {
    expect(unfilledVariables("{{future_key}} {{client_name}}", ["future_key"])).toEqual(["future_key", "client_name"]);
    expect(unfilledVariables("Исправленный ответ", ["future_key"])).toEqual([]);
  });
});
