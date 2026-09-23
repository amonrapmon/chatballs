import { describe, expect, it } from "vitest";

import { renderTemplate, unfilledVariables } from "./templateVariables";

describe("переменные шаблона ответа", () => {
  it("подставляет известные значения", () => {
    const text = renderTemplate("Здравствуйте, {{client_name}}! Меня зовут {{ operator_name }}, {{company}}.", {
      client_name: "Дмитрий",
      operator_name: "Анна",
      company: "Ателье Норд",
    });
    expect(text).toBe("Здравствуйте, Дмитрий! Меня зовут Анна, Ателье Норд.");
  });

  it("оставляет переменную без значения и чужие скобки как есть", () => {
    const text = renderTemplate("Здравствуйте, {{client_name}}! {{unknown}}", { client_name: "  ", company: "Ателье Норд" });
    expect(text).toBe("Здравствуйте, {{client_name}}! {{unknown}}");
  });

  it("находит незаполненные переменные без повторов", () => {
    expect(unfilledVariables("{{client_name}}, {{client_name}} и {{company}}, {{unknown}}")).toEqual(["client_name", "company"]);
    expect(unfilledVariables("Готовый текст")).toEqual([]);
  });
});
