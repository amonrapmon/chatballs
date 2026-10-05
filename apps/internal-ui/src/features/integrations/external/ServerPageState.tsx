import { t } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { ContentState } from "../../../shared/ui";
import { Button } from "../../../shared/ui-controls";
import "./styles.css";

export function ServerPageState({ failed = false, onRetry, onBack }: {
  failed?: boolean;
  onRetry: () => void;
  onBack: () => void;
}) {
  const errorIcon = <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" /><path d="M12 8v4M12 16v.01" />
  </svg>;
  return <ContentState className={`server-page-state${failed ? " is-error" : ""}`}
    icon={failed ? errorIcon : <Icon name="server" size={18} strokeWidth={1.9} />}
    title={t(failed ? "servers.load_failed" : "servers.not_found")}
    text={t(failed ? "servers.load_failed_hint" : "servers.not_found_hint")}
    action={failed ? <Button variant="secondary" onClick={onRetry}>{t("servers.retry")}</Button>
      : <button className="link is-strong" type="button" onClick={onBack}>{t("servers.back")}</button>} />;
}
