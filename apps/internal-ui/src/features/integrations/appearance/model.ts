import type { MessageKey } from "../../../i18n";

export type WidgetAppearance = {
  accent: string;
  launcherIcon: string;
  headerIcon: string | null;
  launcherPosition: "left" | "right";
  launcherSize: 48 | 56 | 64;
  launcherShape: "circle" | "rounded" | "square";
  customCss: string;
};

export const COLOR_PRESETS: ReadonlyArray<{ hex: string; label: MessageKey }> = [
  { hex: "#1677ff", label: "widget_appearance.blue" },
  { hex: "#4f46e5", label: "widget_appearance.indigo" },
  { hex: "#0d8a7e", label: "widget_appearance.teal" },
  { hex: "#15803d", label: "widget_appearance.green" },
  { hex: "#c2410c", label: "widget_appearance.terracotta" },
  { hex: "#be123c", label: "widget_appearance.raspberry" },
  { hex: "#7e22ce", label: "widget_appearance.plum" },
  { hex: "#262626", label: "widget_appearance.graphite" },
];

export const DEFAULT_APPEARANCE: WidgetAppearance = {
  accent: COLOR_PRESETS[0].hex,
  launcherIcon: "",
  headerIcon: "",
  launcherPosition: "right",
  launcherSize: 56,
  launcherShape: "circle",
  customCss: "",
};

export const SHAPE_RADIUS = { circle: "50%", rounded: "30%", square: "10px" };
export const validHex = (value: string): boolean => /^#[0-9a-f]{6}$/i.test(value);

export function readAppearance(config: { accent?: string; appearance?: Partial<WidgetAppearance> }): WidgetAppearance {
  const appearance = { ...DEFAULT_APPEARANCE, ...config.appearance };
  appearance.accent = config.appearance?.accent || config.accent || DEFAULT_APPEARANCE.accent;
  return appearance;
}

export function whiteContrast(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((offset) => {
    const channel = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 1.05 / (0.2126 * r + 0.7152 * g + 0.0722 * b + 0.05);
}

export function appearanceConfig<T extends { accent: string }>(config: T, appearance: WidgetAppearance) {
  return { ...config, accent: appearance.accent, appearance };
}
