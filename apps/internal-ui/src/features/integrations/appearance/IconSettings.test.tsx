import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { t } from "../../../i18n";
import { IconSettings } from "./IconSettings";
import { DEFAULT_APPEARANCE, type WidgetAppearance } from "./model";

const render = (patch: Partial<WidgetAppearance>) => renderToStaticMarkup(
  <IconSettings integrationId={1} appearance={{ ...DEFAULT_APPEARANCE, ...patch }} onChange={() => {}} onBusy={() => {}} />,
);
const links = (html: string) => [...html.matchAll(/<button type="button" class="link is-muted"[^>]*>([^<]+)<\/button>/g)].map((match) => match[1]);

describe("icon settings", () => {
  it("shows the reset and no-icon links by state, as in W3a", () => {
    const none = t("widget_appearance.no_icon");
    const reset = t("widget_appearance.reset");
    expect(links(render({}))).toEqual([none]);
    expect(links(render({ launcherIcon: "/launcher.svg" }))).toEqual([reset, none]);
    expect(links(render({ launcherIcon: "/launcher.svg", headerIcon: "/header.png" }))).toEqual([reset, none, reset]);
    expect(links(render({ headerIcon: null }))).toEqual([reset]);
  });

  it("draws the empty tile and its caption for a header without an icon", () => {
    const html = render({ headerIcon: null });
    expect(html).toContain("widget-icon-tile is-none");
    expect(html).toContain(`<strong>${t("widget_appearance.no_icon")}</strong><small>${t("widget_appearance.no_icon_note")}</small>`);
    expect(render({})).not.toContain("is-none");
  });
});
