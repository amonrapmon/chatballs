import { t } from "../../../i18n";
import type { KnowledgeCategory, KnowledgeItem } from "./model";
import type { ParsedKnowledgeYaml } from "./parseKnowledgeYaml";

export type ImportAction = "create" | "update" | "error";

export type ImportRow = {
  document: ParsedKnowledgeYaml["documents"][number];
  action: ImportAction;
  path: string;
  note: string;
};

export const ACTION_LABEL: Record<ImportAction, string> = {
  create: t("ai.create"),
  update: t("ai.update"),
  error: t("ai.error"),
};

/** Разрешает путь категории в дерево организации: путь ищется по уровням. */
function resolvePath(categories: KnowledgeCategory[], path: string[]): number | null {
  let parentId: number | null = null;
  for (const name of path) {
    const found: KnowledgeCategory | undefined = categories.find(
      (category) => category.parentId === parentId && category.name === name,
    );
    if (!found) return null;
    parentId = found.id;
  }
  return parentId;
}

export function planRows(
  parsed: ParsedKnowledgeYaml,
  categories: KnowledgeCategory[],
  items: KnowledgeItem[],
): ImportRow[] {
  const byTitle = new Map(items.map((item) => [item.title, item]));
  return parsed.documents.map((document) => {
    const existing = byTitle.get(document.title) ?? null;
    const categoryId = document.categoryPath ? resolvePath(categories, document.categoryPath) : null;
    const categoryNote = document.categoryPath && categoryId === null ? t("ai.import_category_creation") : "";
    const path = document.categoryPath ? document.categoryPath.join(" / ") : t("ai.not_given");
    if (!existing) {
      return {
        document,
        action: "create",
        path,
        note: document.categoryPath ? categoryNote : t("ai.will_land_no_category"),
      };
    }
    const samePlace = categoryId !== null && categoryId === existing.category.id;
    return {
      document,
      action: "update",
      path,
      note: categoryNote || (samePlace
        ? t("ai.category_file_matches_current_one")
        : t("ai.title_matched_text_will_replaced")),
    };
  });
}
