import { allPages } from "../../shared/allPages";
import { shortDate } from "../../shared/utils";
import { fetchAllKnowledge, fetchKnowledgeCategories } from "../ai/knowledge/api";
import { categoryRows } from "../ai/knowledge/knowledgeLibraryModel";
import { knowledgeCategoryPath } from "../ai/knowledge/knowledgeTree";
import { listPortalArticles, listSupportPortals } from "../support-portals/api";
import { t } from "../../i18n";

// Что можно выдать агенту: материалы библиотеки и опубликованные статьи
// порталов. Набор разложен по категориям библиотеки и по порталам — сплошным
// списком в организации с сотней материалов ничего не найти.

export type KnowledgeChoice = {
  key: string;
  kind: "knowledge" | "article";
  id: number;
  title: string;
  meta: string;
};

export type ChoiceGroup = {
  key: string;
  title: string;
  icon: "folder" | "globe";
  choices: KnowledgeChoice[];
};

/** Все материалы и статьи, разложенные по категориям и порталам. */
export async function loadChoiceGroups(): Promise<ChoiceGroup[]> {
  const [categories, items] = await Promise.all([fetchKnowledgeCategories(), fetchAllKnowledge()]);
  // Порталы и статьи тоже приходят страницами: диалогу нужен весь набор,
  // иначе статья со второй страницы портала агенту недоступна.
  const portals = await allPages((page) => listSupportPortals(undefined, page));
  const articleLists = await Promise.all(
    portals.map((portal) => allPages((page) => listPortalArticles(portal.id, undefined, page))),
  );

  const byCategory = new Map<number, KnowledgeChoice[]>();
  items.forEach((item) => {
    const choices = byCategory.get(item.category.id) ?? [];
    choices.push({
      key: `k${item.id}`,
      kind: "knowledge",
      id: item.id,
      title: item.title,
      meta: item.isEnabled ? t("ai.updated_on", { date: shortDate(item.updatedAt) }) : t("common.off"),
    });
    byCategory.set(item.category.id, choices);
  });

  // Порядок категорий — тот же, что в дереве библиотеки; название группы —
  // полный путь, иначе две «Общие» в разных ветках не различить.
  const groups: ChoiceGroup[] = categoryRows(categories.items)
    .filter(({ category }) => (byCategory.get(category.id) ?? []).length > 0)
    .map(({ category }) => ({
      key: `c${category.id}`,
      title: knowledgeCategoryPath(categories.items, category.id) || category.name,
      icon: "folder" as const,
      choices: byCategory.get(category.id) ?? [],
    }));

  // Категория материала могла не приехать в справочник (её удалили из-под
  // открытой карточки) — такие материалы всё равно должны быть видны.
  const shown = new Set(groups.flatMap((group) => group.choices.map((choice) => choice.key)));
  const orphans = items
    .filter((item) => !shown.has(`k${item.id}`))
    .map((item): KnowledgeChoice => ({
      key: `k${item.id}`,
      kind: "knowledge",
      id: item.id,
      title: item.title,
      meta: item.category.name,
    }));
  if (orphans.length > 0) {
    groups.push({ key: "c0", title: t("ai.other_knowledge"), icon: "folder", choices: orphans });
  }

  portals.forEach((portal, index) => {
    const choices = articleLists[index]
      .filter((article) => article.status === "PUBLISHED")
      .map((article): KnowledgeChoice => ({
        key: `a${article.id}`,
        kind: "article",
        id: article.id,
        title: article.publishedRevision?.title ?? article.slug,
        meta: t("ai.portal_named", { name: portal.name }),
      }));
    if (choices.length > 0) {
      groups.push({ key: `p${portal.id}`, title: portal.name, icon: "globe", choices });
    }
  });

  return groups;
}

/** Группы с материалами, подходящими под запрос; пустые группы уходят. */
export function filterGroups(groups: ChoiceGroup[], search: string): ChoiceGroup[] {
  const needle = search.trim().toLowerCase();
  if (!needle) return groups;
  return groups
    .map((group) => ({ ...group, choices: group.choices.filter((choice) => choice.title.toLowerCase().includes(needle)) }))
    .filter((group) => group.choices.length > 0);
}

export function pickedInGroup(group: ChoiceGroup, picked: ReadonlySet<string>): number {
  return group.choices.filter((choice) => picked.has(choice.key)).length;
}

/** Идентификаторы выбранного по видам — то, что уходит на сервер. */
export function pickedIds(groups: ChoiceGroup[], picked: ReadonlySet<string>) {
  const chosen = groups.flatMap((group) => group.choices).filter((choice) => picked.has(choice.key));
  return {
    knowledgeIds: chosen.filter((choice) => choice.kind === "knowledge").map((choice) => choice.id),
    articleIds: chosen.filter((choice) => choice.kind === "article").map((choice) => choice.id),
  };
}
