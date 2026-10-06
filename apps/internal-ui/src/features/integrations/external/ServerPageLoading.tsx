import { t } from "../../../i18n";
import "./styles.css";

// X9: шапка-каркас и центральный индикатор загрузки.
export function ServerPageLoading() {
  return <section className="server-page-loading" role="status" aria-label={t("servers.loading")}>
    <header><i /><span><i /><i /></span></header>
    <div><svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-9-9" /></svg>{t("servers.loading")}</div>
  </section>;
}
