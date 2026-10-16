import { describe, expect, it } from "vitest";
import { orderedExample, schemaWithOrder } from "./schemaOrder";
import { schemaRows, type SchemaNode } from "./schema";

describe("schema order across JSONB saves", () => {
  it("keeps explicit order after property keys are reordered by storage", () => {
    const schema: SchemaNode = { type: "object", properties: {
      total: { type: "number", order: 2 }, items: { type: "list", order: 1, items: { type: "string" } },
      order_no: { type: "string", order: 0 },
    } };
    const normalized = schemaWithOrder(schema);
    expect(schemaRows(normalized).map((row) => row.name)).toEqual(["order_no", "items", "total"]);
    expect(Object.keys(orderedExample({ total: 3, items: [], extra: false, order_no: "1" }, normalized) as object))
      .toEqual(["order_no", "items", "total", "extra"]);
  });
  it("recovers legacy display order from references without rewriting sources or values", () => {
    const schema: SchemaNode = { type: "object", properties: { total: { type: "number" }, order_no: { type: "string" } } };
    const normalized = schemaWithOrder(schema, "{{ order_no }}\n{{ total }}");
    expect(schemaRows(normalized).map((row) => row.name)).toEqual(["order_no", "total"]);
    expect(schema.properties!.total.order).toBeUndefined();
    expect(orderedExample({ total: "два", order_no: "1" }, normalized)).toEqual({ order_no: "1", total: "два" });
  });
});
