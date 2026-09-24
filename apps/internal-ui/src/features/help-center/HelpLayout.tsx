import type { ReactNode } from "react";

import { LogoIcon } from "../../shared/icons";
import { HelpSearch } from "./HelpSearch";
import { HelpNavigation } from "./HelpNavigation";
import { PortalWebWidget } from "./PortalWebWidget";
import type { HelpManifest } from "./types";
import { t } from "../../i18n";

export function HelpLayout({
  manifest,
  children,
  search,
  onSearchChange,
  onSearchSubmit,
  compactHeader = false,
  activeCategoryId = null,
  activeArticleSlug = null,
}: {
  manifest: HelpManifest;
  children: ReactNode;
  search: string;
  onSearchChange: (value: string) => void;
  onSearchSubmit?: (value: string) => void;
  compactHeader?: boolean;
  activeCategoryId?: number | null;
  activeArticleSlug?: string | null;
}) {
  const homeHref = "/";
  const portal = manifest.portal;
  return (
    <div className={`help-center ${compactHeader ? "has-compact-header" : ""}`}>
      <header className="help-header">
        <div className="help-header-row">
          <a className="help-brand" href={homeHref}>
            <span className="help-brand-mark"><LogoIcon /></span>
            <span>{portal.name}</span>
          </a>
        </div>
        {compactHeader && (
          <HelpSearch
            compact
            value={search}
            onChange={onSearchChange}
            onSubmit={onSearchSubmit}
          />
        )}
      </header>
      <main className="help-page-grid">
        <HelpNavigation
          manifest={manifest}
          activeCategoryId={activeCategoryId}
          activeArticleSlug={activeArticleSlug}
        />
        <div className="help-page-content">{children}</div>
      </main>
      <footer className="help-footer">
        <div className="help-footer-row">
          <a className="help-footer-brand" href={homeHref}>
            <span className="help-brand-mark"><LogoIcon /></span>
            <span>{portal.name}</span>
          </a>
          <span>{t("portals.knowledge_base_support")}</span>
        </div>
        <span className="help-footer-powered">
          {t("portals.powered_by")}{" "}
          <a href="https://chatballs.ru" target="_blank" rel="noopener noreferrer">Chatballs</a>
        </span>
      </footer>
      {portal.webWidgetKey && <PortalWebWidget widgetKey={portal.webWidgetKey} />}
    </div>
  );
}
