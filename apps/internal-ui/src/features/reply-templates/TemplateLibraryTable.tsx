import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { Pagination } from "../../shared/Pagination";
import { EmptyState, LoadingState } from "../../shared/ui";
import type { ReplyTemplateRef } from "../conversations/model";
import type { TemplateLibraryState } from "./useTemplateLibrary";

const HEAD = ["templates.column_template", "templates.category", "templates.tags", "templates.changed"] as const;

// Кадры N3, N4, N8: строки библиотеки. Без права на область вместо действий —
// замок с причиной; пустой результат фильтра не выдаётся за пустую библиотеку.

export function TemplateLibraryTable({ library, onEdit, onDelete }: {
  library: TemplateLibraryState;
  onEdit: (item: ReplyTemplateRef) => void;
  onDelete: (item: ReplyTemplateRef) => void;
}) {
  const items = library.result?.items ?? [];
  const filtered = Boolean(library.q.trim() || library.categoryId || library.tagIds.length);
  return (
    <>
      <div className="template-library-row template-library-head">
        {HEAD.map((key) => <span key={key}>{t(key)}</span>)}
        <span />
      </div>
      {library.loading && <LoadingState variant="inline" />}
      {!library.loading && library.error && <EmptyState title={library.error} />}
      {!library.loading && !library.error && items.length === 0 && !filtered && <EmptyState title={t("settings.no_templates_yet")} />}
      {!library.loading && items.map((item) => (
        <div className="template-library-row" key={item.id}>
          <div className="template-library-title">
            <strong>{item.title}</strong>
            <small>{item.text.replace(/\s+/g, " ")}</small>
          </div>
          <div className="template-chip-list">
            {library.categories.filter((category) => category.id === item.categoryId).map((category) => <b className="template-category-chip" key={category.id}>{category.name}</b>)}
          </div>
          <div className="template-chip-list">
            {library.tags.filter((tag) => item.tagIds.includes(tag.id)).map((tag) => <b className="template-tag-chip" key={tag.id}># {tag.name}</b>)}
          </div>
          <span className="template-library-changed">{fmt.shortDate(item.updatedAt)}</span>
          <div className="settings-group-actions">
            {library.canManage ? (
              <>
                <button aria-label={t("common.edit")} title={t("common.edit")} type="button" onClick={() => onEdit(item)}><Icon name="edit" size={14} /></button>
                <button aria-label={t("common.delete")} title={t("common.delete")} className="is-danger" type="button" onClick={() => onDelete(item)}><Icon name="trash" size={14} /></button>
              </>
            ) : (
              <span className="template-library-lock" role="img" aria-label={t("templates.readonly_row")} title={t("templates.readonly_row")}><Icon name="lock" size={14} /></span>
            )}
          </div>
        </div>
      ))}
      {!library.loading && !library.error && items.length === 0 && filtered && (
        <p className="template-library-note">
          {noResultsText(library)} <button className="link" type="button" onClick={library.reset}>{t("templates.reset")}</button>
        </p>
      )}
      {!library.loading && library.result && items.length > 0 && (
        <Pagination
          page={library.result.page}
          pageCount={library.result.pageCount}
          onPage={library.setPage}
          note={t("templates.shown", { count: fmt.number(items.length), total: fmt.number(library.result.total) })}
        />
      )}
    </>
  );
}

function noResultsText(library: TemplateLibraryState): string {
  const query = library.q.trim();
  const category = library.categories.find((item) => item.id === library.categoryId)?.name;
  if (query && category) return t("templates.no_results_query_category", { query, category });
  if (query) return t("templates.no_results_query", { query });
  if (category) return t("templates.no_results_category", { category });
  return t("templates.no_results");
}
