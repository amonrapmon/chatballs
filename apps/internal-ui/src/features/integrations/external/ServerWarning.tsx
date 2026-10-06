import { t } from "../../../i18n";
import { helpArticleUrl } from "../../../shared/help";

export function ServerWarning() {
  return <div className="server-warning">
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
    <p>{t("servers.spoof_warning")}{" "}<a className="link" href={helpArticleUrl("instrumenty-agenta")} target="_blank" rel="noopener noreferrer">{t("servers.help")}</a></p>
  </div>;
}
