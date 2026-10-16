import { useState } from "react";

import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { FilterDropdown, SearchInput } from "../../shared/ui-controls";
import { TemplateScopeTabs } from "./TemplateScopeTabs";
import type { TemplateLibraryState } from "./useTemplateLibrary";

// Кадр N3: вкладки областей со счётчиками, поиск по названию и тексту,
// фильтры одной категории и нескольких тегов, переход к «Категориям и тегам».

export function TemplateLibraryToolbar({ library, onTaxonomy }: { library: TemplateLibraryState; onTaxonomy: () => void }) {
  const [open, setOpen] = useState<"category" | "tags" | null>(null);
  const category = library.categories.find((item) => item.id === library.categoryId);
  const tags = library.tags.filter((item) => library.tagIds.includes(item.id));
  return (
    <div className="template-library-toolbar">
      <TemplateScopeTabs value={library.scope} counts={library.counts} onChange={(scope) => { if (scope) library.setScope(scope); }} />
      <SearchInput className="template-library-search" placeholder={t("templates.search")} value={library.q} onChange={library.setQ} />
      <FilterDropdown
        caption={t("templates.category")}
        label={category?.name ?? t("templates.all")}
        open={open === "category"}
        options={library.categories.map((item) => ({ value: String(item.id), label: item.name }))}
        selected={category ? [String(category.id)] : []}
        onOpenChange={(next) => setOpen(next ? "category" : null)}
        onSelect={(value) => {
          library.setCategoryId(library.categoryId === Number(value) ? null : Number(value));
          setOpen(null);
        }}
      />
      <FilterDropdown
        caption={t("templates.tags")}
        label={tags.length === 1 ? `# ${tags[0].name}` : t("templates.all")}
        multiple
        open={open === "tags"}
        options={library.tags.map((item) => ({ value: String(item.id), label: `# ${item.name}` }))}
        selected={library.tagIds.map(String)}
        onOpenChange={(next) => setOpen(next ? "tags" : null)}
        onSelect={(value) => {
          const id = Number(value);
          library.setTagIds(library.tagIds.includes(id) ? library.tagIds.filter((item) => item !== id) : [...library.tagIds, id]);
        }}
      />
      <span className="template-library-spacer" />
      <button className="link is-muted has-icon" type="button" onClick={onTaxonomy}>
        <Icon name="settings" size={14} strokeWidth={1.9} />{t("templates.taxonomy")}
      </button>
    </div>
  );
}
