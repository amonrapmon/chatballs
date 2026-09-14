import { describe, expect, it } from "vitest";
import { t } from "../../../i18n";
import { planRows } from "./knowledgeImportPlan";
import { parseKnowledgeYaml } from "./parseKnowledgeYaml";
import type { KnowledgeCategory, KnowledgeItem } from "./types";

const categories: KnowledgeCategory[] = [
  { id: 1, name: "Root", parentId: null, sortOrder: 0, isSystem: false, knowledgeCount: 0 },
  { id: 2, name: "Child", parentId: 1, sortOrder: 0, isSystem: false, knowledgeCount: 0 },
  { id: 3, name: "Other", parentId: null, sortOrder: 0, isSystem: false, knowledgeCount: 0 },
  { id: 4, name: "Child", parentId: 3, sortOrder: 0, isSystem: false, knowledgeCount: 0 },
];
const existing: KnowledgeItem = {
  id: 10, title: "Existing", description: "", category: categories[1],
  isEnabled: true, attachments: [], agentsCount: 0, fragmentsCount: 0,
  createdAt: "", updatedAt: "",
};

describe("knowledge import preview", () => {
  it("allows an entirely new category tree from YAML", () => {
    const parsed = parseKnowledgeYaml("documents:\n  - title: New\n    content: Text\n    categoryPath: [New root, New child]");
    const [row] = planRows(parsed, [], []);
    expect(row.action).toBe("create");
    expect(row.path).toBe("New root / New child");
    expect(row.note).toBe(t("ai.import_category_creation"));
  });

  it("allows missing descendants and updates existing documents", () => {
    const [row] = planRows({ documents: [
      { title: existing.title, content: "Text", categoryPath: ["Root", "New child"] },
    ] }, categories, [existing]);
    expect(row.action).toBe("update");
    expect(row.note).toBe(t("ai.import_category_creation"));
  });

  it("compares the full path instead of only the leaf name", () => {
    const rows = planRows({ documents: [
      { title: existing.title, content: "Text", categoryPath: ["Other", "Child"] },
      { title: existing.title, content: "Text", categoryPath: ["Root", "Child"] },
    ] }, categories, [existing]);
    expect(rows[0].note).toBe(t("ai.title_matched_text_will_replaced"));
    expect(rows[1].note).toBe(t("ai.category_file_matches_current_one"));
  });

  it("keeps documents without a path importable", () => {
    const [row] = planRows({ documents: [{ title: "New", content: "Text" }] }, [], []);
    expect(row.action).toBe("create");
    expect(row.note).toBe(t("ai.will_land_no_category"));
  });
});
