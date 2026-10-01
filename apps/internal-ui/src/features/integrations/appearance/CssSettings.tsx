import { t } from "../../../i18n";
import { helpArticleUrl } from "../../../shared/help";

export function CssSettings({ value, onChange }: { value: string; onChange: (css: string) => void }) {
  return <div className="widget-appearance-card widget-css-settings">
    <div className="widget-css-heading">
      <label className="widget-appearance-label" htmlFor="widget-custom-css">{t("widget_appearance.css")}</label>
      <a className="link" href={helpArticleUrl("klassy-vidzheta")} target="_blank" rel="noreferrer">{t("widget_appearance.classes")}</a>
    </div>
    <textarea id="widget-custom-css" value={value} onChange={(event) => onChange(event.target.value)} spellCheck={false} />
    <small className="widget-appearance-hint">{t("widget_appearance.css_hint")}</small>
  </div>;
}
