import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { t } from "../i18n";
import { PORTAL_SETTINGS_SECTIONS } from "../features/support-portals/sections";
import { SectionMenu } from "./SectionMenu";

describe("SectionMenu", () => {
  it("keeps planned sections visible without opening them", () => {
    const markup = renderToStaticMarkup(
      <SectionMenu
        items={[{ key: "basics", label: t("portals.basics"), icon: "settings" }, { key: "fields", label: t("settings.site_data"), icon: "code", disabled: true }]}
        activeKey="basics"
        onSelect={() => undefined}
      />,
    );
    expect(markup).toContain(t("settings.site_data"));
    expect(markup).toContain('disabled=""');
  });

  it("renders the portal sections, hint, divider, and dangerous item", () => {
    const items = PORTAL_SETTINGS_SECTIONS.map((item) => ({
      ...item,
      hint: item.key === "domain" ? { text: t("portals.working"), tone: "ok" as const } : undefined,
    }));
    const markup = renderToStaticMarkup(
      <SectionMenu
        items={items}
        activeKey="domain"
        note={t("portals.changes_reach_public_pages_as")}
        onSelect={() => undefined}
      />,
    );

    expect(markup).toContain('class="section-menu"');
    expect(markup.match(/class="section-menu-item/g)).toHaveLength(5);
    expect(markup).toContain('class="section-menu-item is-active"');
    expect(markup).toContain('class="section-menu-item is-danger"');
    expect(markup).toContain('class="section-menu-divider"');
    expect(markup).toContain('class="is-ok">' + t("portals.working"));
    expect(markup).toContain(t("portals.changes_reach_public_pages_as"));
    expect(markup).toContain("<svg");
  });
});
