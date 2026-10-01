import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import articleYaml from "./articles/klassy-vidzheta.yml?raw";
import plan from "./chatballs.json";
import { widgetClasses } from "../../apps/web-chat/src/widgetClasses";
import { helpArticleUrl } from "../../apps/internal-ui/src/shared/help";
import { parseArticleYaml } from "../../apps/internal-ui/src/features/support-portals/parseArticleYaml";
import { MarkdownContent, parseMarkdown } from "../../apps/internal-ui/src/features/help-center/MarkdownContent";

const { articles: [article] } = parseArticleYaml(articleYaml);

describe("widget classes help article", () => {
  it("documents every stable class exactly once with a purpose", () => {
    const rows = [...article.content.matchAll(/^\| `(cb-[a-z-]+)` \| (.+) \|$/gm)];
    expect(rows.map((row) => row[1]).sort()).toEqual(Object.values(widgetClasses).sort());
    expect(rows.every((row) => row[2].trim().length > 0)).toBe(true);

    const html = renderToStaticMarkup(createElement(MarkdownContent, { content: article.content }));
    expect(html).toContain("<table>");
    expect(html).toContain('class="language-css"');
    const sample = parseMarkdown(article.content).blocks.find((block) => block.kind === "code");
    if (!sample) throw new Error("Missing CSS example");
    const sampleClasses = [...sample.text.matchAll(/\.(cb-[a-z-]+)\s*\{/g)].map((match) => match[1]);
    expect(sampleClasses.length).toBeGreaterThan(0);
    for (const name of sampleClasses) expect(Object.values(widgetClasses)).toContain(name);
  });

  it("registers the importable article next to web widget help with reciprocal links", () => {
    expect(article.title).toBe("Классы виджета");
    expect(article.locale).toBe(plan.locale);
    expect(article.categoryPath).toEqual(["Точки входа"]);
    const entries: string[] = plan.order["entry-points"];
    expect(entries[entries.indexOf("veb-vidzhet") + 1]).toBe(article.slug);
    expect(Object.values(plan.order).flat().filter((slug) => slug === article.slug)).toHaveLength(1);
    expect(plan.related["veb-vidzhet"]).toContain(article.slug);
    const related: Record<string, string[]> = plan.related;
    expect(related[article.slug]).toContain("veb-vidzhet");
    expect(helpArticleUrl(article.slug)).toBe("https://chatballs.com.edevs.tech/articles/klassy-vidzheta");
  });
});
