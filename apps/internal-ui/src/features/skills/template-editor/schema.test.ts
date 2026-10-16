import { describe, expect, it } from "vitest";
import { applyField, fieldDraft, nodeAt, parentOptions, removeField, schemaRows, type SchemaNode } from "./schema";

const schema: SchemaNode = { type: "object", properties: {
  items: { type: "list", items: { type: "object", properties: { qty: { type: "number", required: true } } } },
  info: { type: "object", properties: {} },
} };
describe("typed schema edits", () => {
  it("edits nested fields immutably and preserves list/object children", () => {
    const draft = { ...fieldDraft(schema, "items"), name: "lines" };
    const next = applyField(schema, draft, "items");
    expect(nodeAt(next, "lines/[]/qty")?.type).toBe("number");
    expect(nodeAt(next, "items")).toBeUndefined();
    expect(nodeAt(schema, "items/[]/qty")?.required).toBe(true);
    expect(schemaRows(next).map((row) => row.path)).toEqual(["lines", "lines/[]/qty", "info"]);
    expect(removeField(next, "lines").properties?.info.type).toBe("object");
  });
  it("rejects missing parents, descendants, scalar parents, duplicate names and depth overflow", () => {
    const draft = fieldDraft(schema, "items");
    for (const parent of ["unknown", "items/[]", "items/[]/qty"]) {
      expect(() => applyField(schema, { ...draft, parent }, "items")).toThrow();
    }
    expect(parentOptions(schema, "items").map(([path]) => path)).toEqual(["", "info"]);
    expect(() => applyField(schema, { ...fieldDraft(schema), name: "info" })).toThrow();
    expect(() => applyField(schema, { ...fieldDraft(schema), name: "bad-name" })).toThrow();
    expect(() => applyField(schema, { ...fieldDraft(schema), name: "deep", types: Array(9).fill("list") })).toThrow();
  });
  it("uses the same controls for scalar and nested lists and reparenting", () => {
    const next = applyField(schema, { ...fieldDraft(schema), name: "values", parent: "info", types: ["list", "list", "number"] });
    expect(nodeAt(next, "info/values/[]/[]")?.type).toBe("number");
    expect(parentOptions(next).map(([path]) => path)).not.toContain("info/values/[]");
    const moved = applyField(next, { ...fieldDraft(next, "items/[]/qty"), parent: "info" }, "items/[]/qty");
    expect(nodeAt(moved, "info/qty")?.type).toBe("number");
    expect(nodeAt(moved, "items/[]/qty")).toBeUndefined();
  });
});
