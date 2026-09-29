import { useEffect, useState } from "react";

import { SectionMenu } from "../../shared/SectionMenu";
import {
  listPortalWidgets,
  type PortalAddressConfig,
  type PortalWidgetOption,
  type SupportPortal,
} from "./model";
import { PortalAppearanceSettings } from "./PortalAppearanceSettings";
import { PortalBasicsSettings } from "./PortalBasicsSettings";
import { PortalDomainSettings } from "./PortalDomainSettings";
import { PortalPublishSettings } from "./PortalPublishSettings";
import { PortalWidgetSettings } from "./PortalWidgetSettings";
import {
  PORTAL_SETTINGS_SECTIONS,
  type PortalSettingsSectionKey,
} from "./sections";
import { t } from "../../i18n";

// Настройки портала (дизайн-базлайн v2, кадры PT4–PT6): не модалка на 960px с
// пятью секциями подряд, а страница с субменю разделов 250px.

export function PortalSettings({
  address,
  canManage,
  portal,
  section,
  onChanged,
  openSection,
}: {
  address: PortalAddressConfig;
  canManage: boolean;
  portal: SupportPortal;
  section: PortalSettingsSectionKey;
  onChanged: (portal: SupportPortal) => void;
  openSection: (section: PortalSettingsSectionKey) => void;
}) {
  const [anonymousWidgets, setAnonymousWidgets] = useState<PortalWidgetOption[]>([]);

  useEffect(() => {
    listPortalWidgets(portal.id)
      .then((payload) => setAnonymousWidgets(payload.items))
      .catch(() => setAnonymousWidgets([]));
  }, [portal.id]);

  const current = PORTAL_SETTINGS_SECTIONS.find((item) => item.key === section)
    ?? PORTAL_SETTINGS_SECTIONS[0];
  const domainLive = Boolean(portal.customDomain && portal.customDomainVerifiedAt);
  const menuItems = PORTAL_SETTINGS_SECTIONS.map((item) => ({
    ...item,
    hint: item.key === "domain" && domainLive ? { text: t("portals.working"), tone: "ok" as const } : undefined,
  }));

  return (
    <div className="portal-settings-layout">
      <SectionMenu
        items={menuItems}
        activeKey={current.key}
        note={t("portals.changes_reach_public_pages_as")}
        onSelect={openSection}
      />

      <div className="portal-settings-content">
        <div className="portal-settings-inner">
          <div className="portal-settings-heading">
            <h3>{current.heading}</h3>
            <p>{current.lead}</p>
          </div>

          {current.key === "basics" && (
            <PortalBasicsSettings address={address} canManage={canManage} portal={portal} onChanged={onChanged} />
          )}
          {current.key === "domain" && (
            <PortalDomainSettings canManage={canManage} portal={portal} onChanged={onChanged} />
          )}
          {current.key === "theme" && (
            <PortalAppearanceSettings canManage={canManage} portal={portal} onChanged={onChanged} />
          )}
          {current.key === "widget" && (
            <PortalWidgetSettings canManage={canManage} portal={portal} widgets={anonymousWidgets} onChanged={onChanged} />
          )}
          {current.key === "danger" && (
            <PortalPublishSettings canManage={canManage} portal={portal} onChanged={onChanged} />
          )}
        </div>
      </div>
    </div>
  );
}
