import { t } from "../../../i18n";
import { ShieldIcon } from "../../../shared/icons";
import { helpArticleUrl } from "../../../shared/help";

export function ServerWarning() {
  return <div className="server-warning">
    <ShieldIcon />
    <p>{t("servers.spoof_warning")}{" "}<a className="link" href={helpArticleUrl("instrumenty-agenta")} target="_blank" rel="noopener noreferrer">{t("servers.help")}</a></p>
  </div>;
}
