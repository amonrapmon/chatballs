import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Role, SessionUser } from "../types";
import { t } from "../i18n";
import { HELP_CENTER_URL, helpArticleUrl } from "../shared/help";
import { SidebarNavigation } from "./SidebarNavigation";
import { Sidebar } from "./Sidebar";
import { RealtimeProvider } from "../features/realtime/RealtimeProvider";

// SSR проверяет именно видимость пунктов: эффекты обновления сессии и API
// здесь не выполняются, состояние аккаунтов штатного контура не меняется.
function userWith(role: Role, reportCapabilities: string[] = []) {
  const user: SessionUser = {
    id: 1, email: "user@example.test", fullName: "User", mustChangePassword: false,
    totpEnabled: false, totpLastUsedAt: null, deliveryMode: "CLOUD", isInstanceAdmin: false,
    uiTheme: "SYSTEM", uiAccent: "", uiLanguage: "", language: "ru", memberships: [],
    organizationPublicId: "org", organization: "org", organizationName: "Org",
    organizationLogoUrl: null, role, positionTitle: "", totpRequired: false,
    capabilities: [], groups: [], joinedAt: "2026-01-01T00:00:00Z", reportCapabilities,
  };
  return user;
}

function render(role: Role, reportCapabilities: string[] = []) {
  const user = userWith(role, reportCapabilities);
  return renderToStaticMarkup(
    <SidebarNavigation route="chat" user={user} setRoute={() => undefined} waitingCount={0}
      chatScope={{ kind: "all" }} setChatScope={() => undefined} chatCounters={null} />,
  );
}

describe("sidebar navigation", () => {
  it.each(["OWNER", "ADMIN"] as const)("keeps the baseline order for %s", (role) => {
    const html = render(role);
    const labels = ["common.chat", "common.contacts", "common.agents", "common.operators", "common.portals", "common.knowledge_base", "reports.title", "common.settings", "navigation.help"] as const;
    const positions = labels.map((key) => html.indexOf(`<span>${t(key)}</span>`));
    expect(positions.every((position) => position >= 0)).toBe(true);
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
    const divider = html.indexOf('class="hub-nav-divider"');
    expect(divider).toBeGreaterThan(positions[5]);
    expect(divider).toBeLessThan(positions[6]);
  });

  it.each(["EMPLOYEE", "SUPERVISOR"] as const)("shows help after the tree and statistics only with the grant for %s", (role) => {
    for (const allowed of [false, true]) {
      const html = render(role, allowed ? ["reports.view"] : []);
      expect(html.includes(`<span>${t("reports.title")}</span>`)).toBe(allowed);
      expect(html).not.toContain(`<span>${t("common.settings")}</span>`);
      expect(html.indexOf('class="hub-nav-divider"')).toBeLessThan(html.indexOf(`<span>${t("navigation.help")}</span>`));
      if (allowed) expect(html.indexOf(`<span>${t("reports.title")}</span>`)).toBeLessThan(html.indexOf(`<span>${t("navigation.help")}</span>`));
    }
  });

  it("uses a native safe help link and preserves article URLs", () => {
    const html = render("EMPLOYEE");
    expect(html).toContain(`href="${HELP_CENTER_URL}" target="_blank" rel="noopener noreferrer"`);
    expect(html).toContain(`title="${t("navigation.help_tooltip")}"`);
    expect(helpArticleUrl("agent")).toBe(`${HELP_CENTER_URL}articles/agent`);
  });

  it("keeps an organization logo in both the rail and full menu", () => {
    const logoUrl = "/api/v1/organizations/org/logo/";
    const html = renderToStaticMarkup(
      <RealtimeProvider><Sidebar route="chat" user={{ ...userWith("ADMIN"), organizationLogoUrl: logoUrl }}
        setRoute={() => undefined} onLogout={() => undefined} onSwitchOrganization={() => undefined}
        chatScope={{ kind: "all" }} setChatScope={() => undefined} chatCounters={null}
        expanded={false} setExpanded={() => undefined} /></RealtimeProvider>,
    );
    expect(html.match(new RegExp(`src="${logoUrl}"`, "g"))).toHaveLength(2);
    expect(html).not.toContain('class="chatballs-logo"');
    expect(html.match(/hub-brand-mark has-logo/g)).toHaveLength(2);
  });
});
