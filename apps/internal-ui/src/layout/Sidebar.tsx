import type { CSSProperties } from "react";

import type { RouteKey, SessionUser } from "../types";
import { useResizableWidth } from "../shared/useResizableWidth";
import { Icon, LogoIcon } from "../shared/icons";
import { SidebarNavigation } from "./SidebarNavigation";
import { NavigationIcon } from "./NavigationIcon";
import type { DialogScope } from "../features/conversations/ConversationWorkspace";
import { type ConversationCounters } from "../features/conversations/model";
import { SidebarUserMenu } from "./SidebarUserMenu";
import { OrganizationSwitcher } from "./OrganizationSwitcher";
import { t } from "../i18n";
import { useOwnWorkStatus } from "../features/work-status/useOwnWorkStatus";
import { PresenceDot, WorkStatusIcon } from "../features/work-status/WorkStatusLabel";
import { statusLabel } from "../features/work-status/model";

export function Sidebar({
  route,
  user,
  setRoute,
  onLogout,
  onSwitchOrganization,
  waitingCount = 0,
  chatScope,
  setChatScope,
  chatCounters,
  unreadCount = 0,
  onOpenNotifications,
  expanded: railExpanded,
  setExpanded: setRailExpanded,
}: {
  route: RouteKey;
  user: SessionUser;
  setRoute: (route: RouteKey) => void;
  onLogout: () => void;
  onSwitchOrganization: (organizationPublicId: string) => void;
  waitingCount?: number;
  chatScope: DialogScope;
  setChatScope: (scope: DialogScope) => void;
  chatCounters: ConversationCounters | null;
  unreadCount?: number;
  onOpenNotifications?: () => void;
  expanded: boolean;
  setExpanded: (expanded: boolean) => void;
}) {
  // Ширина сайдбара: тянется за правый край (180–320px), запоминается в браузере.
  const sidebarWidth = useResizableWidth("sidebar", { fallback: 220, min: 180, max: 320 });
  const workStatus = useOwnWorkStatus();
  // Рейка (кадр K6): статус — иконкой у аватара и словами в подсказке.
  const railTitle = [user.fullName || user.email, workStatus.saved && statusLabel(workStatus.saved.status)].filter(Boolean).join(" · ");
  // Кадр S2: на ≤1024px сайдбар сжимается в рейку 60px; «развернуть»
  // раскрывает полный сайдбар поверх контента (состояние — в Shell, его же
  // открывает ☰ мобильной шапки чата, кадр M1).
  const initials = (user.fullName || user.email)
    .split(/\s+/)
    .map((part) => part[0] ?? "")
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <aside className={`hub-sidebar ${railExpanded ? "is-rail-expanded" : ""} ${sidebarWidth.dragging ? "is-resizing" : ""}`} style={{ "--sidebar-width": `${sidebarWidth.width}px` } as CSSProperties}>
      <div className="pane-resizer" role="separator" aria-orientation="vertical" aria-label={t("profile.sidebar_width")} title={t("profile.drag_resize_double_click_reset")} onPointerDown={sidebarWidth.onPointerDown} onDoubleClick={sidebarWidth.reset} />
      <div className="hub-rail">
        <div className={`hub-brand-mark ${user.organizationLogoUrl ? "has-logo" : ""}`}>
          {user.organizationLogoUrl ? <img src={user.organizationLogoUrl} alt="" /> : <LogoIcon />}
        </div>
        <button
          className={`hub-rail-button ${route === "chat" ? "is-active" : ""}`}
          title={t("common.chat")}
          type="button"
          onClick={() => setRoute("chat")}
        >
          <Icon name="message" size={18} strokeWidth={1.9} />
        </button>
        <button className="hub-rail-button" title={t("profile.expand")} type="button" onClick={() => setRailExpanded(true)}>
          <NavigationIcon name="expand" />
        </button>
        <div className="hub-rail-spacer" />
        <button className="hub-rail-avatar" title={railTitle} type="button" onClick={() => setRailExpanded(true)}>
          {initials}
          <PresenceDot online={workStatus.online} own />
          {workStatus.saved && <WorkStatusIcon code={workStatus.saved.status} size={14} />}
        </button>
      </div>
      {railExpanded && <button className="hub-rail-backdrop" aria-label={t("profile.collapse_menu")} type="button" onClick={() => setRailExpanded(false)} />}
      <div className="hub-sidebar-body" onClick={() => setRailExpanded(false)}>
      <OrganizationSwitcher user={user} setRoute={setRoute} onSwitchOrganization={onSwitchOrganization} />
      <SidebarNavigation route={route} user={user} setRoute={setRoute} waitingCount={waitingCount} chatScope={chatScope} setChatScope={setChatScope} chatCounters={chatCounters} />
      <SidebarUserMenu user={user} route={route} setRoute={setRoute} onLogout={onLogout} unreadCount={unreadCount} onOpenNotifications={onOpenNotifications} workStatus={workStatus} />
      </div>
    </aside>
  );
}
