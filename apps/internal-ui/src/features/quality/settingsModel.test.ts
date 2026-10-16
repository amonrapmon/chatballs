import { describe, expect, it } from "vitest";
import { changeCriterionScale, suggestedCriteria } from "./settingsModel";
import { serializeCriteria } from "./serialization";
import type { QualityCriterion, QualitySettings } from "./types";

// Unit inputs only; no replacement backend or installed demo data.
const greeting: QualityCriterion = { code: "greeting", name: "Greeting", description: "Greeted and introduced themselves",
  scale: ["Yes", "No"], reporting: { positiveValue: "Yes" } };
const initial: QualitySettings = { enabled: false, criteriaVersion: null, nextCriteriaVersion: 1, criteriaCreatedAt: null,
  criteria: [], scales: [], criteriaValueLiterals: {}, suggestedCriteria: [greeting] };

describe("unsaved quality criteria suggestions", () => {
  it("offers editable copies without changing persisted settings or the proposed source", () => {
    const before = JSON.stringify(initial);
    const proposed = suggestedCriteria(initial)!;
    proposed[0].name = "Edited";
    proposed[0].description = "Custom description";
    proposed[0].scale[0] = "Changed";
    proposed[0].reporting!.positiveValue = "Changed";
    expect(JSON.stringify(initial)).toBe(before);
    expect(initial.enabled).toBe(false);
    expect(initial.criteriaVersion).toBeNull();
    expect(suggestedCriteria(initial)![0]).toEqual(greeting);
  });
  it("preserves saved and explicitly cleared versions instead of substituting examples", () => {
    expect(suggestedCriteria({ ...initial, criteriaVersion: 1, criteria: [greeting] })).toBeNull();
    expect(suggestedCriteria({ ...initial, criteriaVersion: 2, criteria: [] })).toBeNull();
    expect(suggestedCriteria({ ...initial, criteria: [greeting] })).toBeNull();
    expect(suggestedCriteria({ ...initial, suggestedCriteria: null })).toBeNull();
  });
  it("serializes edited proposals only as explicit save input, including an empty set", () => {
    const proposed = suggestedCriteria(initial)!;
    proposed[0].description = "Edited";
    expect(JSON.parse(serializeCriteria(proposed, initial))[0].description).toBe("Edited");
    expect(serializeCriteria([], initial)).toBe("[]");
    expect(initial.criteria).toEqual([]);
  });
  it("keeps valid binary reporting and removes it when choosing a numeric scale", () => {
    expect(changeCriterionScale(greeting, ["No", "Yes"]).reporting).toEqual({ positiveValue: "Yes" });
    const numeric = changeCriterionScale(greeting, [1, 2, 3, 4, 5]);
    expect(numeric.scale).toEqual([1, 2, 3, 4, 5]);
    expect(numeric.reporting).toBeUndefined();
    expect(greeting.scale).toEqual(["Yes", "No"]);
  });
});
