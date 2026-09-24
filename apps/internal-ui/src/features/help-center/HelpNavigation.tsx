import { useEffect, useMemo, useState } from "react";

import { fetchHelpArticles } from "./api";
import { HelpChevronIcon } from "./HelpIcons";
import type { HelpArticle, HelpCategory, HelpManifest } from "./types";
import { t } from "../../i18n";

function articleHref(slug: string): string {
  return `/articles/${encodeURIComponent(slug)}/`;
}

type BranchProps = {
  category: HelpCategory;
  childrenByParent: Map<number | null, HelpCategory[]>;
  activePath: Set<number>;
  activeCategoryId: number | null;
  activeArticleSlug: string | null;
  locale: string;
};

function CategoryBranch({
  category, childrenByParent, activePath, activeCategoryId, activeArticleSlug, locale,
}: BranchProps) {
  const [expanded, setExpanded] = useState(activePath.has(category.id));
  const [articles, setArticles] = useState<HelpArticle[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const children = childrenByParent.get(category.id) ?? [];

  useEffect(() => {
    if (activePath.has(category.id)) setExpanded(true);
  }, [activePath, category.id]);

  useEffect(() => {
    if (!expanded || articles !== null || category.articleCount === 0) return;
    let cancelled = false;
    setLoading(true);
    fetchHelpArticles({ locale, category: category.slug, direct: true, limit: 50 })
      .then((payload) => {
        if (cancelled) return;
        setArticles(payload.items);
        setHasMore(payload.pagination.hasMore);
        setFailed(false);
      })
      .catch(() => { if (!cancelled) setFailed(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [articles, category.articleCount, category.slug, expanded, locale]);

  async function loadMore() {
    if (loading || !articles) return;
    setLoading(true);
    try {
      const payload = await fetchHelpArticles({
        locale, category: category.slug, direct: true, limit: 50, offset: articles.length,
      });
      setArticles((current) => [...(current ?? []), ...payload.items]);
      setHasMore(payload.pagination.hasMore);
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }

  const canExpand = category.articleCount > 0 || children.length > 0;
  return (
    <li className="help-nav-branch">
      <div className="help-nav-row">
        <a
          aria-current={activeCategoryId === category.id && !activeArticleSlug ? "page" : undefined}
          className={activeCategoryId === category.id ? "is-current" : ""}
          href={`/?category=${encodeURIComponent(category.slug)}`}
        >{category.name}</a>
        {canExpand && (
          <button
            aria-label={t(expanded ? "portals.collapse_section" : "portals.expand_section", { name: category.name })}
            aria-expanded={expanded}
            className={expanded ? "is-expanded" : ""}
            type="button"
            onClick={() => setExpanded((value) => !value)}
          ><HelpChevronIcon /></button>
        )}
      </div>
      {canExpand && expanded && (
        <ul className="help-nav-children">
          {articles?.map((article) => (
            <li key={article.slug}>
              <a
                aria-current={activeArticleSlug === article.slug ? "page" : undefined}
                className={`help-nav-article${activeArticleSlug === article.slug ? " is-current" : ""}`}
                href={articleHref(article.slug)}
              >{article.revision.title}</a>
            </li>
          ))}
          {children.map((child) => (
            <CategoryBranch
              key={child.id}
              category={child}
              childrenByParent={childrenByParent}
              activePath={activePath}
              activeCategoryId={activeCategoryId}
              activeArticleSlug={activeArticleSlug}
              locale={locale}
            />
          ))}
          {loading && <li className="help-nav-status" aria-live="polite">…</li>}
          {failed && <li className="help-nav-status">{t("portals.could_not_load_articles")}</li>}
          {hasMore && !loading && (
            <li><button className="help-nav-more" type="button" onClick={() => void loadMore()}>{t("portals.show_more")}</button></li>
          )}
        </ul>
      )}
    </li>
  );
}

export function HelpNavigation({
  manifest, activeCategoryId, activeArticleSlug,
}: {
  manifest: HelpManifest;
  activeCategoryId: number | null;
  activeArticleSlug: string | null;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const childrenByParent = useMemo(() => {
    const result = new Map<number | null, HelpCategory[]>();
    for (const category of manifest.categories) {
      const siblings = result.get(category.parentId) ?? [];
      siblings.push(category);
      result.set(category.parentId, siblings);
    }
    for (const siblings of result.values()) {
      siblings.sort((a, b) => a.sortOrder - b.sortOrder || a.name.localeCompare(b.name));
    }
    return result;
  }, [manifest.categories]);
  const activePath = useMemo(() => {
    const byId = new Map(manifest.categories.map((category) => [category.id, category]));
    const path = new Set<number>();
    let current = activeCategoryId ? byId.get(activeCategoryId) : undefined;
    while (current && !path.has(current.id)) {
      path.add(current.id);
      current = current.parentId ? byId.get(current.parentId) : undefined;
    }
    return path;
  }, [activeCategoryId, manifest.categories]);

  return (
    <aside className="help-navigation">
      <button
        aria-controls="help-navigation-tree"
        aria-expanded={mobileOpen}
        className="help-navigation-mobile-toggle"
        type="button"
        onClick={() => setMobileOpen((value) => !value)}
      >{t("portals.all_sections")}<HelpChevronIcon /></button>
      <nav aria-label={t("portals.navigation")} className={mobileOpen ? "is-open" : ""} id="help-navigation-tree">
        <a className="help-nav-all" href="/">{t("portals.all_sections")}</a>
        <ul>
          {(childrenByParent.get(null) ?? []).map((category) => (
            <CategoryBranch
              key={category.id}
              category={category}
              childrenByParent={childrenByParent}
              activePath={activePath}
              activeCategoryId={activeCategoryId}
              activeArticleSlug={activeArticleSlug}
              locale={manifest.portal.defaultLocale}
            />
          ))}
        </ul>
      </nav>
    </aside>
  );
}
