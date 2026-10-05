import { t } from "../../../i18n";
import { Icon } from "../../../shared/icons";

// X9: шапка-каркас и центральный индикатор загрузки.
export function ServerPageLoading() {
  return <section className="server-page-loading" role="status" aria-label={t("servers.loading")}>
    <header><i /><span><i /><i /></span></header>
    <div><Icon name="refresh" size={15} />{t("servers.loading")}</div>
  </section>;
}
