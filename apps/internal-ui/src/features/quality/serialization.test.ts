import { expect, it } from "vitest";
import { serializeCriteria } from "./serialization";

it("retains server numeric literals when only a criterion name is edited", () => {
  const criteria = [{ code: "resolution", name: "Решение", description: "Описание", scale: [1, 1, 9007199254740992] }];
  const saved = { criteria, criteriaValueLiterals: { resolution: ["1", "1.0", "9007199254740993"] } };
  const encoded = serializeCriteria([{ ...criteria[0], name: "Новое название" }], saved);
  expect(encoded).toContain('"scale":[1,1.0,9007199254740993]');
  expect(JSON.parse(encoded)[0].name).toBe("Новое название");
});

it("preserves explicit positive values when saving an edited criterion", () => {
  const criteria = [{ code: "greeting", name: "Greeting", description: "Public greeting", scale: ["Yes", "No"], reporting: { positiveValue: "Yes" } }];
  const saved = { criteria, criteriaValueLiterals: {} };
  expect(JSON.parse(serializeCriteria([{ ...criteria[0], name: "Renamed" }], saved))[0].reporting).toEqual({ positiveValue: "Yes" });
});
