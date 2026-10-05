import { t } from "../../../i18n";
import { SHAPE_RADIUS, type WidgetAppearance } from "./model";
import { WidgetIcon } from "./WidgetIcon";
import "./preview.css";

/** Упрощённая копия из W3; демонстрационные реплики принадлежат макету. */
export function AppearancePreview({ appearance }: { appearance: WidgetAppearance }) {
  const side = { [appearance.launcherPosition]: 16 };
  return <aside className="widget-appearance-preview" aria-label={t("widget_appearance.preview")}>
    <span className="widget-preview-label">{t("widget_appearance.preview")}</span>
    <div className="widget-preview-site">
      <span className="widget-preview-domain">{t("widget_appearance.preview_page", { domain: "obed.ru" })}</span>
      <div className="widget-preview-panel" style={{ ...side, bottom: appearance.launcherSize + 28 }}>
        <div className="widget-preview-header">
          <WidgetIcon url={appearance.headerIcon === "" ? appearance.launcherIcon : appearance.headerIcon} size={28} />
          <span>{t("widget_appearance.preview_agent")}</span>
          <i><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M5 12h14" /></svg></i>
        </div>
        <div className="widget-preview-body">
          <div className="widget-preview-bubble is-agent">{t("widget_appearance.preview_greeting")}</div>
          <div className="widget-preview-bubble is-client">{t("widget_appearance.preview_client")}</div>
        </div>
        <div className="widget-preview-composer"><span>{t("widget_appearance.preview_message")}</span><i><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5m-7 7 7-7 7 7" /></svg></i></div>
      </div>
      <div className="widget-preview-launcher" style={{ ...side, width: appearance.launcherSize, height: appearance.launcherSize, borderRadius: SHAPE_RADIUS[appearance.launcherShape] }}>
        <WidgetIcon url={appearance.launcherIcon} size={Math.round(appearance.launcherSize * 0.55)} />
      </div>
    </div>
  </aside>;
}
