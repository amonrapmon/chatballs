import { HelpArrowIcon } from "./HelpIcons";
import type { HelpArticle } from "./types";
import { t } from "../../i18n";

export function HelpRelatedArticles({ articles }: { articles: HelpArticle[] }) {
  if (articles.length === 0) return null;
  return (
    <section className="help-related" aria-labelledby="help-related-title">
      <h2 id="help-related-title">{t("portals.related_articles")}</h2>
      <ul>
        {articles.map((article) => (
          <li key={article.slug}>
            <a href={`/articles/${encodeURIComponent(article.slug)}/`}>
              <span>{article.revision.title}</span>
              <HelpArrowIcon />
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
