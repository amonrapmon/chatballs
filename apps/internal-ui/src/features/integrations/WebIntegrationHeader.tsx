import { t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { CopyButton } from "../../shared/ui-controls";
import { webWidgetSnippet, type Integration } from "./model";

export function WebIntegrationHeader({ integration, onOpenSettings, onBack }: {
  integration: Integration;
  onOpenSettings: () => void;
  onBack: () => void;
}) {
  const snippet = integration.webChatWidget ? webWidgetSnippet(integration.webChatWidget.publicKey) : "";
  const working = integration.isActive && integration.status === "OK";

  return (
    <header className="web-integration-head">
      <nav className="portal-breadcrumbs">
        <button className="link is-strong" type="button" onClick={onOpenSettings}>{t("common.settings")}</button>
        <span>/</span>
        <button className="link is-muted" type="button" onClick={onBack}>{t("common.integrations")}</button>
        <span>/</span><b>{integration.name}</b>
      </nav>
      <div className="web-integration-title">
        <span className="web-integration-icon"><Icon name="message" size={17} strokeWidth={1.9} /></span>
        <h2>{integration.name}</h2>
        {working && <span className="web-integration-status">{t("portals.working")}</span>}
        <span className="web-integration-agent">
          {integration.channel
            ? t("settings.web_integration_agent", { name: integration.channel.name })
            : t("common.web_widget")}
        </span>
      </div>
      {snippet && <div className="web-integration-embed">
        <span className="web-integration-embed-code">
          <code>{snippet}</code>
          <CopyButton value={snippet} className="web-integration-copy" />
        </span>
        <span>{t("settings.embed_before_body_end")}</span>
      </div>}
    </header>
  );
}
