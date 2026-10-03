import { describe, expect, it } from "vitest";

import { appearanceConfig, COLOR_PRESETS, DEFAULT_APPEARANCE, headerIconRow, headerIconUrl, launcherIconRow, readAppearance, validHex, whiteContrast } from "./model";

describe("widget appearance", () => {
  it("reads legacy color and preserves the header icon's three states", () => {
    expect(readAppearance({ accent: "#0d8a7e" })).toEqual({ ...DEFAULT_APPEARANCE, accent: "#0d8a7e" });
    for (const headerIcon of [null, "", "/icon.svg"]) {
      expect(readAppearance({ accent: "#1677ff", appearance: { accent: "#c2410c", headerIcon } }))
        .toMatchObject({ accent: "#c2410c", headerIcon });
    }
  });

  it("offers «Сбросить» and «Без иконки» by icon state, as in W3a", () => {
    expect(launcherIconRow(DEFAULT_APPEARANCE)).toMatchObject({ url: "", caption: "widget_appearance.agent_mark", hint: "widget_appearance.launcher_hint", canRemove: false, canReset: false });
    expect(headerIconRow(DEFAULT_APPEARANCE)).toMatchObject({ url: "", caption: "widget_appearance.agent_mark", hint: "widget_appearance.header_hint", canRemove: true, canReset: false });

    const own = { ...DEFAULT_APPEARANCE, launcherIcon: "/launcher.svg" };
    expect(launcherIconRow(own)).toMatchObject({ url: "/launcher.svg", caption: "widget_appearance.own_icon", hint: "widget_appearance.launcher_own_hint", canRemove: false, canReset: true });
    expect(headerIconRow(own)).toMatchObject({ url: "/launcher.svg", caption: "widget_appearance.as_launcher", hint: "widget_appearance.header_hint", canRemove: true, canReset: false });
    expect(headerIconRow({ ...own, headerIcon: "/header.png" })).toMatchObject({ url: "/header.png", caption: "widget_appearance.own_icon", hint: "widget_appearance.header_own_hint", canRemove: true, canReset: true });

    for (const launcherIcon of ["", "/launcher.svg"]) {
      const none = { ...DEFAULT_APPEARANCE, launcherIcon, headerIcon: null };
      expect(headerIconUrl(none)).toBeNull();
      expect(headerIconRow(none)).toEqual({ url: null, caption: "widget_appearance.no_icon", note: "widget_appearance.no_icon_note", hint: "widget_appearance.header_none_hint", canRemove: false, canReset: true });
    }
  });

  it("saves a reset icon as empty and a removed header icon as null", () => {
    const config = { accent: "#1677ff", appearance: { launcherIcon: "/launcher.svg", headerIcon: "/header.png" } };
    const reset = { ...readAppearance(config), launcherIcon: "", headerIcon: "" };
    expect(appearanceConfig(config, reset).appearance).toMatchObject({ launcherIcon: "", headerIcon: "" });
    expect(headerIconUrl(reset)).toBe("");
    expect(appearanceConfig(config, { ...reset, headerIcon: null }).appearance.headerIcon).toBeNull();
  });

  it("calculates white text contrast with the WCAG luminance formula", () => {
    expect(whiteContrast("#000000")).toBeCloseTo(21);
    expect(whiteContrast("#ffffff")).toBeCloseTo(1);
    expect(whiteContrast("#ffd400")).toBeLessThan(4.5);
    expect(whiteContrast("#767676")).toBeGreaterThanOrEqual(4.5);
    expect(whiteContrast("#777777")).toBeLessThan(4.5);
    expect(whiteContrast(COLOR_PRESETS[2].hex)).toBeCloseTo(4.23919);
  });

  it("accepts only full six-digit HEX colors", () => {
    expect(validHex("#ABCdef")).toBe(true);
    for (const value of ["", "#abc", "1677ff", "#abcdefg", "#zzzzzz", "#abcdef;"]) expect(validHex(value)).toBe(false);
  });

  it("updates appearance and legacy accent without losing other configuration", () => {
    const config = { accent: "", fields: [{ key: "order" }], form: { enabled: true }, allowedOrigins: ["example.com"] };
    expect(appearanceConfig(config, DEFAULT_APPEARANCE)).toEqual({ ...config, accent: DEFAULT_APPEARANCE.accent, appearance: DEFAULT_APPEARANCE });
  });
});
