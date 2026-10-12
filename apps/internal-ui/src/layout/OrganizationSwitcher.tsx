import { Dropdown } from "antd";

import type { RouteKey, SessionUser } from "../types";
import { Icon, LogoIcon } from "../shared/icons";
import { canCreateOrganization, defaultRoute } from "../auth/access";
import { t } from "../i18n";

// Переключение организации и переход на её стартовую страницу (кадр A1).
export function OrganizationSwitcher({ user, setRoute, onSwitchOrganization }: {
  user: SessionUser;
  setRoute: (route: RouteKey) => void;
  onSwitchOrganization: (organizationPublicId: string) => void;
}) {
  return (
    <div className="hub-brand">
      <button className={`hub-brand-mark ${user.organizationLogoUrl ? "has-logo" : ""}`} type="button" aria-label={t("profile.go_start_page")} onClick={() => setRoute(defaultRoute(user))}>
        {user.organizationLogoUrl
          ? <img src={user.organizationLogoUrl} alt="" />
          : <LogoIcon />}
      </button>
      {/* Переключатель организации (дизайн-базлайн v2, A1): все организации
          человека, текущая отмечена; выбор другой открывает её стартовый экран. */}
      <Dropdown
        trigger={["click"]}
        placement="bottomLeft"
        overlayClassName="app-dropdown is-wide"
        menu={{
          items: [
            ...user.memberships.map((membership) => ({
              key: membership.organizationPublicId,
              label: (
                <button
                  type="button"
                  className={membership.organizationPublicId === user.organizationPublicId ? "is-checked" : ""}
                  onClick={() => {
                    if (membership.organizationPublicId !== user.organizationPublicId) {
                      onSwitchOrganization(membership.organizationPublicId);
                    }
                  }}
                >
                  <Icon name="building" size={15} />
                  {membership.organizationName || "Chatballs"}
                </button>
              ),
            })),
            // «Добавить организацию» — внизу списка, отделена чертой: ведёт на
            // страницу создания, где человек становится владельцем новой.
            ...(canCreateOrganization(user)
              ? [
                { type: "divider" as const, key: "add-divider" },
                {
                  key: "add-organization",
                  label: (
                    <button type="button" className="hub-brand-add" onClick={() => setRoute("organizationCreate")}>
                      <span className="hub-brand-add-icon"><Icon name="plus" size={11} strokeWidth={2.4} /></span>
                      {t("organizations.add")}
                    </button>
                  ),
                },
              ]
              : []),
          ],
        }}
      >
        <button className="hub-brand-switch" type="button" title={t("profile.switch_organization")}>
          <span>{user.organizationName || "Chatballs"}</span>
          <Icon name="chevron" size={14} />
        </button>
      </Dropdown>
    </div>
  );
}
