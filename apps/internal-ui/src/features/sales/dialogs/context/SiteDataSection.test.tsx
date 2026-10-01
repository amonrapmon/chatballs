import type { SiteField } from "@chatballs/contracts";
import { setCurrentLanguage } from "@chatballs/shared";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fmt } from "../../../../i18n";
import { SiteDataSection } from "./SiteDataSection";
import { isRecentSiteField, nextSiteFieldExpiry, RECENT_SITE_FIELD_MS } from "./siteData";

const updatedAt = "2026-09-30T15:40:00Z";
function field(type: SiteField["type"], value: SiteField["value"], extra: Partial<SiteField> = {}): SiteField {
  return { key: type, label: type, type, value, display: String(value), updatedAt, ...extra };
}

beforeEach(() => { setCurrentLanguage("ru"); });
afterEach(() => vi.useRealTimers());

describe("SiteDataSection", () => {
  it("скрывает пустую секцию и показывает замок с последним обновлением", () => {
    expect(renderToStaticMarkup(<SiteDataSection />)).toBe("");
    expect(renderToStaticMarkup(<SiteDataSection fields={[]} />)).toBe("");
    const latest = "2026-09-30T15:42:00Z";
    const html = renderToStaticMarkup(<SiteDataSection fields={[field("string", "abc"), field("boolean", false, { updatedAt: latest })]} />);
    expect(html).toContain('sales-context-section ctx-site-data');
    expect(html).toContain(`обновлено в ${fmt.time(latest)}`);
    expect(html).toContain("только чтение");
    expect(html).not.toMatch(/<(input|select|textarea)\b/);
  });

  it("показывает оба boolean и цвет/подпись enum из API", () => {
    const html = renderToStaticMarkup(<SiteDataSection fields={[
      field("boolean", true, { key: "yes" }), field("boolean", false, { key: "no" }),
      field("enum", "on_the_way", { display: "В пути", color: "#1677ff" }),
    ]} />);
    expect(html).toContain('is-yes"><i></i>Да');
    expect(html).toContain('is-no"><i></i>Нет');
    expect(html).toContain('--site-field-color:#1677ff');
    expect(html).toContain("В пути");
    expect(html).not.toContain("on_the_way");
  });

  it("форматирует datetime и отделяет обычный текст от ID и номеров", () => {
    const html = renderToStaticMarkup(<SiteDataSection fields={[
      field("string", "u_58213", { key: "user_id" }),
      field("string", "10482", { key: "order_number" }), field("number", 42),
      field("string", "Комментарий"), field("datetime", updatedAt),
    ]} />);
    expect(html.match(/ctx-site-copy/g)).toHaveLength(3);
    expect(html.match(/ctx-site-value is-mono/g)).toHaveLength(3);
    expect(html).toContain(fmt.shortDateTime(updatedAt));
    expect(html).toContain("Комментарий");
  });

  it("даёт стандартные ссылки и копирование email, телефона и URL", () => {
    const html = renderToStaticMarkup(<SiteDataSection fields={[
      field("email", "a@example.com"), field("phone", "+7 (916) 482-15-30"), field("url", "https://example.com/order"),
    ]} />);
    expect(html.match(/class="link ctx-site-value"/g)).toHaveLength(3);
    expect(html.match(/ctx-site-copy/g)).toHaveLength(3);
    expect(html).toContain('href="mailto:a@example.com"');
    expect(html).toContain('href="tel:+79164821530"');
    expect(html).toContain('href="https://example.com/order"');
    const unsafe = renderToStaticMarkup(<SiteDataSection fields={[field("url", "javascript:alert(1)")]} />);
    expect(unsafe).not.toContain('href=');
  });

  it("подсвечивает до границы 10 минут и планирует ближайшее погасание", () => {
    vi.useFakeTimers();
    const row = field("enum", "on_the_way", { display: "В пути" });
    const expiry = Date.parse(updatedAt) + RECENT_SITE_FIELD_MS;
    vi.setSystemTime(expiry - 1);
    let html = renderToStaticMarkup(<SiteDataSection fields={[row]} />);
    expect(html).toContain("ctx-site-row is-recent");
    expect(html).toContain(`ctx-site-changed">${fmt.time(updatedAt)}`);
    expect(nextSiteFieldExpiry([row], Date.now())).toBe(expiry);
    vi.setSystemTime(expiry);
    html = renderToStaticMarkup(<SiteDataSection fields={[row]} />);
    expect(html).not.toContain("is-recent");
    expect(html).not.toContain("ctx-site-changed");
    expect(nextSiteFieldExpiry([row], Date.now())).toBeUndefined();
    expect(isRecentSiteField(row, Date.parse(updatedAt) - 1)).toBe(false);
  });
});
