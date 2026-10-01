import type { CSSProperties } from "react";

import { fmt, t } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { COLOR_PRESETS, validHex, whiteContrast } from "./model";

export function ColorSettings({ accent, customHex, custom, onPreset, onHex }: {
  accent: string; customHex: string; custom: boolean;
  onPreset: (accent: string) => void; onHex: (hex: string) => void;
}) {
  const invalid = custom && !validHex(customHex);
  const ratio = whiteContrast(accent);
  const note = invalid ? t("widget_appearance.hex_format") : t(ratio >= 4.5
    ? "widget_appearance.contrast_ok" : "widget_appearance.contrast_warning", {
    ratio: fmt.number(ratio, { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
  });

  return (
    <div className="widget-appearance-card widget-color-settings">
      <span className="widget-appearance-label">{t("widget_appearance.color")}</span>
      <div className="widget-color-presets">
        {COLOR_PRESETS.map(({ hex, label }) => (
          <button key={hex} type="button" title={t(label)} aria-pressed={(!custom || invalid) && accent.toLowerCase() === hex}
            className="widget-color-preset" style={{ "--swatch": hex } as CSSProperties} onClick={() => onPreset(hex)}>
            <span>{(!custom || invalid) && accent.toLowerCase() === hex && <Icon name="check" size={15} strokeWidth={3} />}</span>
            <small>{t(label)}</small>
          </button>
        ))}
      </div>
      <div className="widget-custom-color-row">
        <label className={`widget-custom-color${custom && !invalid ? " is-selected" : ""}`}>
          <i style={{ background: validHex(customHex) ? customHex : "var(--n-9)" }} />
          <span>{t("widget_appearance.custom")}</span>
          <input aria-label={t("widget_appearance.custom_hex")} aria-describedby="widget-color-note"
            value={customHex} placeholder={t("widget_appearance.hex_placeholder")} onChange={(event) => onHex(event.target.value)} />
        </label>
        <small id="widget-color-note" className={invalid || ratio < 4.5 ? "is-warning" : "is-readable"} aria-live="polite">{note}</small>
      </div>
    </div>
  );
}
