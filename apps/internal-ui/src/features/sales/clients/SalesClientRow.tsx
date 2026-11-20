import { Dropdown, message } from "antd";

import { ChannelGlyph } from "../../../shared/badges";
import { Icon } from "../../../shared/icons";
import { ContactAvatar } from "../../conversations/ContactAvatar";
import type { SalesClientRowVm } from "./model";
import { t } from "../../../i18n";

// Строка контакта (кадр K1). Вся строка кликабельна — открывает карточку.
export function SalesClientRow({ client, menu, openClient, setMenu }: { client: SalesClientRowVm; menu: string | null; openClient: (id: number) => void; setMenu: (menu: string | null) => void }) {
  const menuOpen = menu === client.cid;
  const maxIdentity = client.maxIdentities[0];
  const hasPrimaryContact = Boolean(client.phone || client.email);
  const maxIdentityTitle = client.maxIdentities
    .map((identity) => `MAX · ${identity.integrationName}: ${identity.externalUserId}`)
    .join("\n");
  const maxIdButton = maxIdentity ? (
    <button
      className="sales-client-max-id"
      type="button"
      title={maxIdentityTitle}
      aria-label={`Скопировать MAX ID ${maxIdentity.externalUserId}`}
      onClick={(event) => {
        event.stopPropagation();
        void navigator.clipboard.writeText(maxIdentity.externalUserId)
          .then(() => { void message.success("MAX ID скопирован"); })
          .catch(() => { void message.error("Не удалось скопировать MAX ID"); });
      }}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <span>MAX ID · {maxIdentity.externalUserId}</span>
      {client.maxIdentities.length > 1 && <em>+{client.maxIdentities.length - 1}</em>}
      <Icon name="copy" size={12} />
    </button>
  ) : null;
  const menuItems = [
    { key: "open", label: <button type="button" onClick={() => { setMenu(null); openClient(client.id); }}><Icon name="external" size={15} />{t("admin.open_card")}</button> },
  ];
  return (
    <div className="sales-client-row" role="button" tabIndex={0} onClick={() => openClient(client.id)} onKeyDown={(event) => { if (event.key === "Enter") openClient(client.id); }}>
      <div className="sales-client-person">
        <ContactAvatar avatarUrl={client.avatarUrl || undefined} initials={client.initials} background={client.avatarBg} className="sales-client-avatar" />
        <span>
          <strong>{client.name}</strong>
          <small>{client.cid}</small>
        </span>
      </div>
      <div className="sales-client-contact">
        {maxIdButton && !hasPrimaryContact
          ? maxIdButton
          : <span className={client.anon ? "is-muted" : ""}>{client.contactLine}</span>}
        {maxIdButton && hasPrimaryContact ? maxIdButton : <small>{client.contactSub}</small>}
      </div>
      <div className="sales-client-channels">
        {client.channels.map((channel) => (
          <span style={{ background: channel.bg, color: channel.color }} title={channel.full} key={channel.code}>
            <ChannelGlyph provider={channel.code} size={14} />
          </span>
        ))}
      </div>
      <div className="sales-client-last">
        <i style={{ background: client.lastDot }} />
        <span>
          <span>{client.lastWho}</span>
          <small>{client.lastWhen}</small>
        </span>
      </div>
      <div className="sales-client-open" style={{ color: client.openColor }}>{client.openDialogs}</div>
      <div className="sales-client-menu" onClick={(event) => event.stopPropagation()}>
        <Dropdown menu={{ items: menuItems }} open={menuOpen} onOpenChange={(open) => setMenu(open ? client.cid : null)} trigger={["click"]} overlayClassName="app-dropdown is-wide">
          <button className="row-menu-button" type="button" aria-label={t("sales.contact_actions")}><Icon name="more" /></button>
        </Dropdown>
      </div>
    </div>
  );
}
