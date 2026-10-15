import { Dropdown } from "antd";
import { useEffect, useState } from "react";

import { t } from "../i18n";
import { Icon } from "../shared/icons";
import { loadContactCrmLinks, loadConversationCrmLinks } from "./api";
import { isTrustedCrmUrl, type CrmLink, type CrmLinks } from "./model";

type LinkProps = { scope: "conversation" | "contact"; id: number };

function CrmAnchor({ item }: { item: CrmLink }) {
  return (
    <a className="link has-icon" href={item.url} target="_blank" rel="noopener noreferrer">
      {t("crm.open_profile", { provider: item.provider })}
      <Icon name="external" size={13} />
    </a>
  );
}

export function CrmProfileLink(props: LinkProps) {
  const { id, scope } = props;
  const [result, setResult] = useState<CrmLinks | null>(null);
  useEffect(() => {
    let active = true;
    setResult(null);
    const load = scope === "conversation" ? loadConversationCrmLinks : loadContactCrmLinks;
    load(id).then((value) => {
      if (active) setResult(value);
    }).catch(() => {
      if (active) setResult(null);
    });
    return () => { active = false; };
  }, [id, scope]);

  if (!result || result.state === "disabled" || result.state === "no_phone") return null;
  const links = result.links.filter((item) => isTrustedCrmUrl(item.url, item.provider));
  const warning = ["ambiguous_company", "inactive_company", "no_company", "partial"].includes(result.state);
  if (!links.length && !warning) return null;

  if (scope === "conversation") {
    const item = links[0];
    return (
      <div className="crm-dialog-profile">
        {item && <><CrmAnchor item={item} /><small>{item.companyName}</small></>}
        {warning && <p className="crm-inline-warning">
          {t("crm.link_unbound")} · {t("crm.link_unbound_hint")}
        </p>}
      </div>
    );
  }

  const item = links[0];
  const many = links.length > 1;
  const menuItems = links.map((link) => ({
    key: String(link.companyId),
    label: (
      <a href={link.url} target="_blank" rel="noopener noreferrer" className="link is-neutral has-icon">
        {link.companyName}<Icon name="external" size={13} />
      </a>
    ),
  }));
  return (
    <div className="crm-contact-profile">
      {many ? (
        <Dropdown menu={{ items: menuItems }} overlayClassName="app-dropdown is-wide" trigger={["click"]}>
          <button type="button" className="link has-icon">
            {t("crm.open_in", { provider: item.provider })}
            <Icon name="chevron" size={13} />
          </button>
        </Dropdown>
      ) : item ? <CrmAnchor item={item} /> : null}
      {warning && <small className="crm-inline-warning">{t("crm.partial")}</small>}
    </div>
  );
}
