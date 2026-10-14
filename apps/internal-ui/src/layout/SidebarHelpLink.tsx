import { t } from "../i18n";
import { HELP_CENTER_URL } from "../shared/help";
import { Icon } from "../shared/icons";
import { NavigationIcon } from "./NavigationIcon";

export function SidebarHelpLink() {
  return (
    <a className="link hub-nav-item hub-nav-help" href={HELP_CENTER_URL} target="_blank" rel="noopener noreferrer" title={t("navigation.help_tooltip")}>
      <NavigationIcon name="help" />
      <span>{t("navigation.help")}</span>
      <Icon name="external" size={13} strokeWidth={2} />
    </a>
  );
}
