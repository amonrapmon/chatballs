import { fmt, t } from "../../../i18n";
import { Segmented } from "../../../shared/ui";
import type { WidgetAppearance } from "./model";

export function LauncherSettings({ appearance, onChange }: {
  appearance: WidgetAppearance; onChange: (patch: Partial<WidgetAppearance>) => void;
}) {
  return (
    <div className="widget-appearance-card widget-launcher-settings">
      <div>
        <span className="widget-appearance-label">{t("widget_appearance.position")}</span>
        <Segmented className="portal-scheme-segment" value={appearance.launcherPosition}
          items={[["left", t("widget_appearance.left")], ["right", t("widget_appearance.right")]]}
          setValue={(launcherPosition) => onChange({ launcherPosition })} />
      </div>
      <div>
        <span className="widget-appearance-label">{t("widget_appearance.size")}</span>
        <Segmented className="portal-scheme-segment" value={String(appearance.launcherSize)}
          items={[48, 56, 64].map((size) => [String(size), fmt.number(size)])}
          setValue={(size) => onChange({ launcherSize: Number(size) as WidgetAppearance["launcherSize"] })} />
      </div>
      <div>
        <span className="widget-appearance-label">{t("widget_appearance.shape")}</span>
        <Segmented className="portal-scheme-segment" value={appearance.launcherShape}
          items={[["circle", t("widget_appearance.circle")], ["rounded", t("widget_appearance.rounded")], ["square", t("widget_appearance.square")]]}
          setValue={(launcherShape) => onChange({ launcherShape })} />
      </div>
    </div>
  );
}
