import { t } from "../../../i18n";
import { orderedProperties, schemaWithOrder } from "./schemaOrder";

export const fieldTypes = ["string", "number", "boolean", "object", "list"] as const;
export type FieldType = typeof fieldTypes[number];
export type SchemaNode = {
  type: FieldType;
  required?: boolean;
  description?: string;
  order?: number;
  properties?: Record<string, SchemaNode>;
  items?: SchemaNode;
};
export type FieldRow = { path: string; name: string; node: SchemaNode; depth: number };
export type FieldDraft = { name: string; description: string; parent: string; required: boolean; types: FieldType[] };
export const typeOptions = () => fieldTypes.map((kind): [string, string] => [kind, t(`skill_templates.${kind}`)]);
export const pathLabel = (path: string) => path.replaceAll("/[]", "[]").replaceAll("/", ".");

export function nodeAt(schema: SchemaNode, path: string): SchemaNode | undefined {
  let node: SchemaNode | undefined = schema;
  for (const part of path ? path.split("/") : []) node = part === "[]" ? node?.items : node?.properties?.[part];
  return node;
}
export function schemaRows(schema: SchemaNode) {
  const rows: FieldRow[] = [];
  function visit(node: SchemaNode, path: string, depth: number) {
    if (depth > 8) return;
    for (const [name, child] of orderedProperties(node)) {
      const childPath = path ? `${path}/${name}` : name;
      rows.push({ path: childPath, name, node: child, depth });
      visit(child, childPath, depth + 1);
    }
    if (node.items) visit(node.items, `${path}/[]`, depth);
  }
  visit(schema, "", 0);
  return rows;
}
export function parentOptions(schema: SchemaNode, editing?: string) {
  const options: [string, string][] = [["", t("skill_templates.root")]];
  function visit(node: SchemaNode, path: string, depth: number) {
    if (depth > 8 || (editing && (path === editing || path.startsWith(`${editing}/`)))) return;
    if (path && node.type === "object") options.push([path, pathLabel(path)]);
    for (const [name, child] of Object.entries(node.properties ?? {})) visit(child, path ? `${path}/${name}` : name, depth + 1);
    if (node.items) visit(node.items, `${path}/[]`, depth + 1);
  }
  visit(schema, "", 0);
  return options;
}
export function fieldDraft(schema: SchemaNode, path?: string): FieldDraft {
  const parts = path?.split("/") ?? [];
  const node = path ? nodeAt(schema, path) : undefined;
  const types: FieldType[] = [];
  for (let item = node; item; item = item.type === "list" ? item.items : undefined) types.push(item.type);
  return { name: parts.pop() ?? "", parent: parts.join("/"), description: node?.description ?? "",
    required: node?.required ?? true, types: types.length ? types : ["string"] };
}
export function removeField(schema: SchemaNode, path: string) {
  const next = structuredClone(schema);
  const parts = path.split("/");
  const name = parts.pop()!;
  const parent = nodeAt(next, parts.join("/"));
  if (parent?.properties) delete parent.properties[name];
  return next;
}
export function applyField(schema: SchemaNode, draft: FieldDraft, editing?: string): SchemaNode {
  const name = draft.name.trim();
  if (Array.from(draft.description).length > 500) throw new Error(t("skills.too_long", { count: 500 }));
  if (draft.types.length > 8) throw new Error(t("skill_templates.depth"));
  if (!/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(name)) throw new Error(t("skill_templates.invalid_name"));
  if (!parentOptions(schema, editing).some(([path]) => path === draft.parent)) throw new Error(t("skill_templates.invalid_parent"));
  const ordered = schemaWithOrder(schema);
  const next = editing ? removeField(ordered, editing) : structuredClone(ordered);
  const parent = nodeAt(next, draft.parent);
  if (!parent || parent.type !== "object" || !parent.properties) throw new Error(t("skill_templates.invalid_parent"));
  if (Object.hasOwn(parent.properties, name)) throw new Error(t("skill_templates.duplicate"));
  let previous = editing ? nodeAt(ordered, editing) : undefined;
  const oldParent = editing?.split("/").slice(0, -1).join("/");
  const order = oldParent === draft.parent ? previous?.order : Object.keys(parent.properties).length;
  const build = (index: number): SchemaNode => {
    const type = draft.types[index] ?? "string";
    const old = previous;
    previous = old?.type === "list" ? old.items : undefined;
    return { type, ...(type === "object" ? { properties: old?.type === "object" ? old.properties : {} } : {}),
      ...(type === "list" ? { items: build(index + 1) } : {}) };
  };
  parent.properties[name] = { ...build(0), required: draft.required, description: draft.description, order };
  function depth(node: SchemaNode, level: number): number {
    return Math.max(level, ...Object.values(node.properties ?? {}).map((child) => depth(child, level + 1)),
      node.items ? depth(node.items, level + 1) : 0);
  }
  if (depth(next, 0) > 8) throw new Error(t("skill_templates.depth"));
  return next;
}
