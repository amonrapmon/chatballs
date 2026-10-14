import type { CSSProperties } from "react";

import type { RouteKey, SessionUser } from "../types";
import { useResizableWidth } from "../shared/useResizableWidth";
import { Icon, LogoIcon } from "../shared/icons";
import { isManager } from "../auth/access";
import { useSupervision } from "../auth/useSupervision";
import type { TourTarget } from "../features/onboarding/steps";
import type { DialogScope } from "../features/conversations/ConversationWorkspace";
import { type ConversationCounters } from "../features/conversations/model";
import { SidebarUserMenu } from "./SidebarUserMenu";
import { ChatScopeTree } from "./ChatScopeTree";
import { OrganizationSwitcher } from "./OrganizationSwitcher";
import { t } from "../i18n";
import { useOwnWorkStatus } from "../features/work-status/useOwnWorkStatus";
import { PresenceDot, WorkStatusIcon } from "../features/work-status/WorkStatusLabel";
import { statusLabel } from "../features/work-status/model";

// Сайдбар по дизайн-базлайну v2: у менеджера — плоские семь пунктов (A1, KB1) и
// блок «Запуск»; у сотрудника разделов нет (§3) — сайдбар и есть фильтр списка
// диалогов: дерево «Все диалоги · Группы · Агенты» + профиль внизу.

type SidebarLinkProps = {
  activeRoutes?: RouteKey[];
  badge?: string;
  icon: Parameters<typeof Icon>[0]["name"];
  label: string;
  route: RouteKey;
  routeKey: RouteKey;
  setRoute: (route: RouteKey) => void;
  // Имя цели для тура онбординга: по нему «Показать где» находит пункт на экране.
  target?: TourTarget;
};

function SidebarLink({ activeRoutes, badge, icon, label, route, routeKey, setRoute, target }: SidebarLinkProps) {
  const active = activeRoutes?.includes(route) ?? routeKey === route;
  return (
    <button
      className={`hub-nav-item ${active ? "is-active" : ""}`}
      type="button"
      data-onboarding-target={target}
      onClick={() => setRoute(routeKey)}
    >
      <Icon name={icon} />
      {label}
      {badge && <b className="hub-nav-badge">{badge}</b>}
    </button>
  );
}

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
  const manager = isManager(user);
  const supervision = useSupervision(user);
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
          <Icon name="message" size={18} />
        </button>
        <button className="hub-rail-button" title={t("profile.expand")} type="button" onClick={() => setRailExpanded(true)}>
          <Icon name="chevron" size={17} />
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
      {manager ? (
        <nav className="hub-nav">
          <SidebarLink icon="message" label={t("common.chat")} badge={waitingCount > 0 ? String(waitingCount) : undefined} route={route} routeKey="chat" setRoute={setRoute} />
          <SidebarLink activeRoutes={["salesClients", "salesClientDetail"]} icon="user" label={t("common.contacts")} route={route} routeKey="salesClients" setRoute={setRoute} />
          <SidebarLink activeRoutes={["agents", "agentDetail"]} icon="robot" label={t("common.agents")} route={route} routeKey="agents" setRoute={setRoute} target="nav-agents" />
          <SidebarLink activeRoutes={["employees", "employeeDetail"]} icon="team" label={t("common.operators")} route={route} routeKey="employees" setRoute={setRoute} target="nav-employees" />
          <SidebarLink activeRoutes={["supportPortals", "supportPortalDetail", "supportPortalSettings"]} icon="globe" label={t("common.portals")} route={route} routeKey="supportPortals" setRoute={setRoute} />
          <SidebarLink activeRoutes={["knowledge", "knowledgeDetail", "knowledgeCreate", "knowledgeEdit", "knowledgeCategories", "knowledgeImport"]} icon="book" label={t("common.knowledge_base")} route={route} routeKey="knowledge" setRoute={setRoute} target="nav-knowledge" />
          <div className="hub-nav-divider" />
          <SidebarLink icon="grid" label={t("reports.title")} route={route} routeKey="supportReports" setRoute={setRoute} />
          <SidebarLink activeRoutes={["settings", "webIntegrationSettings", "mcpServerCreate", "httpServerCreate", "administrationAudit"]} icon="settings" label={t("common.settings")} route={route} routeKey="settings" setRoute={setRoute} />
        </nav>
      ) : route === "profile" || route === "replyTemplates" ? (
        /* Кадр P2: на «Профиле» у сотрудника сайдбар без навигации — фильтровать
           нечего, дерево диалогов относится только к чату. Так же устроена
           страница «Шаблоны ответов» из меню пользователя. */
        null
      ) : (
        <ChatScopeTree
          supervision={supervision}
          route={route}
          scope={chatScope}
          counters={chatCounters}
          setScope={(scope) => {
            setChatScope(scope);
            setRoute("chat");
          }}
        />
      )}
      <SidebarUserMenu user={user} route={route} setRoute={setRoute} onLogout={onLogout} unreadCount={unreadCount} onOpenNotifications={onOpenNotifications} workStatus={workStatus} />
      </div>
    </aside>
  );
}
