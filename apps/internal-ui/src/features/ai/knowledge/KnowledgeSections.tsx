import { useMemo, useState } from "react";

import { Icon } from "../../../shared/icons";
import { t } from "../../../i18n";
import { categoryRows, visibleCategoryRows } from "./knowledgeLibraryModel";
import type { KnowledgeCategory } from "./model";

// Левая панель библиотеки знаний (кадр KB1): дерево категорий.
//
// Ветку с вложенными категориями сворачивают шевроном — у организации с
// трёхуровневым деревом список иначе занимает панель целиком. Свёрнутое
// помнит браузер: человек возвращается в раздел к тому же виду, что оставил.

const STORAGE_KEY = "chatballs.ui.knowledge.collapsed";

function readCollapsed(): Set<number> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const stored = raw ? (JSON.parse(raw) as unknown) : null;
    return new Set(Array.isArray(stored) ? stored.filter((item): item is number => typeof item === "number") : []);
  } catch {
    return new Set();
  }
}

function rememberCollapsed(collapsed: Set<number>): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...collapsed]));
  } catch {
    /* без хранилища дерево просто не помнит свёрнутое между заходами */
  }
}

export function KnowledgeSections({ categories, selected, canManage, onSelect, onManage }: {
  categories: KnowledgeCategory[];
  selected: number | undefined;
  canManage: boolean;
  onSelect: (categoryId: number | undefined) => void;
  onManage: () => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<number>>(readCollapsed);
  const rows = useMemo(() => categoryRows(categories), [categories]);
  const visible = useMemo(() => visibleCategoryRows(rows, collapsed), [rows, collapsed]);
  const total = categories
    .filter((category) => category.parentId === null)
    .reduce((sum, category) => sum + (category.knowledgeCount ?? 0), 0);

  function toggle(categoryId: number) {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(categoryId)) next.delete(categoryId);
      else next.add(categoryId);
      rememberCollapsed(next);
      return next;
    });
  }

  return (
    <aside className="knowledge-sections">
      <header>
        <span>{t("ai.categories")}</span>
        {canManage && <button type="button" onClick={onManage}>{t("ai.manage")}</button>}
      </header>
      <nav>
        <div className={`knowledge-section-row${selected === undefined ? " is-active" : ""}`}>
          <i className="knowledge-section-twist" />
          <button className="knowledge-section-pick" type="button" onClick={() => onSelect(undefined)}>
            <Icon name="folder" size={15} strokeWidth={1.8} />
            <span>{t("ai.all_knowledge")}</span>
            <small>{total}</small>
          </button>
        </div>
        {visible.map(({ category, depth, count, hasChildren }) => {
          const open = !collapsed.has(category.id);
          return (
            <div
              className={`knowledge-section-row${selected === category.id ? " is-active" : ""}`}
              key={category.id}
              style={{ paddingLeft: depth * 16 }}
            >
              {hasChildren ? (
                <button
                  aria-expanded={open}
                  aria-label={open
                    ? t("ai.collapse_category", { name: category.name })
                    : t("ai.expand_category", { name: category.name })}
                  className={`knowledge-section-twist${open ? " is-open" : ""}`}
                  type="button"
                  onClick={() => toggle(category.id)}
                >
                  <Icon name="chevronRight" size={13} strokeWidth={2.2} />
                </button>
              ) : (
                <i className="knowledge-section-twist" />
              )}
              <button className="knowledge-section-pick" type="button" onClick={() => onSelect(category.id)}>
                <span>{category.name}</span>
                <small>{count}</small>
              </button>
            </div>
          );
        })}
      </nav>
      {canManage && (
        <div className="knowledge-sections-foot">
          <button type="button" onClick={onManage}>
            <Icon name="plus" size={14} strokeWidth={2} />{t("ai.add_category")}</button>
        </div>
      )}
    </aside>
  );
}
