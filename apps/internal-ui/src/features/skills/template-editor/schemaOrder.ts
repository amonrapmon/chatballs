import type { SchemaNode } from "./schema";

export const orderedProperties = (schema: SchemaNode) => Object.entries(schema.properties ?? {})
  .sort(([, left], [, right]) => (left.order ?? Number.MAX_SAFE_INTEGER) - (right.order ?? Number.MAX_SAFE_INTEGER));

/** JSONB does not preserve object-key order. Old copies use source references
 * as a deterministic fallback; new edits persist explicit presentation order.
 * Neither source nor customer values are changed by this normalization.
 */
export function schemaWithOrder(schema: SchemaNode, source = ""): SchemaNode {
  const rank = new Map<string, number>();
  for (const match of source.matchAll(/\{\{\s*(?:#(?:each|if)\s+)?([A-Za-z][A-Za-z0-9_.]*)\s*\}\}/g)) {
    for (const part of match[1].split(".")) if (!rank.has(part)) rank.set(part, match.index);
  }
  function visit(node: SchemaNode): SchemaNode {
    const properties = Object.entries(node.properties ?? {}).sort(([a, left], [b, right]) =>
      (left.order ?? rank.get(a) ?? Number.MAX_SAFE_INTEGER) - (right.order ?? rank.get(b) ?? Number.MAX_SAFE_INTEGER));
    return { ...node,
      ...(node.properties ? { properties: Object.fromEntries(properties.map(([name, child], order) => [name, { ...visit(child), order }])) } : {}),
      ...(node.items ? { items: visit(node.items) } : {}),
    };
  }
  return visit(schema);
}

export function orderedExample(value: unknown, schema: SchemaNode): unknown {
  if (Array.isArray(value)) return value.map((item) => schema.items ? orderedExample(item, schema.items) : item);
  if (!value || typeof value !== "object") return value;
  const data = value as Record<string, unknown>;
  const known = orderedProperties(schema).filter(([name]) => Object.hasOwn(data, name))
    .map(([name, child]) => [name, orderedExample(data[name], child)]);
  const unknown = Object.entries(data).filter(([name]) => !Object.hasOwn(schema.properties ?? {}, name));
  return Object.fromEntries([...known, ...unknown]);
}
