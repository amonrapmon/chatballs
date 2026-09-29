import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { t } from "../i18n";
import { PORTAL_SETTINGS_SECTIONS } from "../features/support-portals/sections";
import { SectionMenu } from "./SectionMenu";

describe("SectionMenu", () => {
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
