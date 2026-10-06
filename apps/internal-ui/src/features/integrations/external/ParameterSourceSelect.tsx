import { Dropdown } from "antd";
import { t } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import type { Integration } from "../model";
import { sourceFromKey, sourceKey, sourceLabel } from "./model";
import type { ParameterSource } from "./types";

export function ParameterSourceSelect({ source, integrations, onChange, disabled, label, details = false }: {
  source: ParameterSource; integrations: Integration[]; onChange: (source: ParameterSource) => void; disabled?: boolean; label?: string; details?: boolean;
}) {
  const items = [
    ...(!details ? [{ key: "ai", icon: <Icon name="sparkles" size={14} />, label: <span>{t("servers.ai_source")}<small className="server-menu-hint">{t("servers.ai_source_menu_hint")}</small></span> }, { type: "divider" as const }] : []),
    { type: "group" as const, label: t("servers.customer_group"), children: ["name", "email", "phone"].map((field) => ({
      key: `contact:${field}`, icon: <Icon name={field === "name" ? "user" : field === "email" ? "mail" : "phone"} size={14} />, label: sourceLabel({ type: "contact", field: field as "name" | "email" | "phone" }, integrations),
    })) },
    ...integrations.filter((i) => i.provider === "WEB" && i.config.fields?.length).map((i) => ({
      type: "group" as const, label: t("servers.custom_group", { name: i.name }),
      children: i.config.fields!.map((field) => ({ key: `web:${i.id}:${field.key}`, icon: <Icon name="code" size={14} />, label: <span>{field.label}{sourceKey(source) === `web:${i.id}:${field.key}` && <small className="server-menu-hint">{t("servers.web_source_menu_hint")}</small>}</span> })),
    })),
  ];
  return <Dropdown trigger={["click"]} disabled={disabled} overlayClassName="app-dropdown server-source-menu"
    menu={{ items, selectable: true, selectedKeys: [sourceKey(source)], onClick: ({ key }) => onChange(sourceFromKey(key)) }}>
    <button className={`server-source-select${source.type !== "ai" ? " is-bound" : ""}`} type="button" disabled={disabled}
      aria-label={label ?? t("servers.parameter_source")}>
      <Icon name={source.type === "ai" ? "sparkles" : details && source.type === "web_field" ? "code" : "link"} size={13} />
      <span>{sourceLabel(source, integrations)}{details && source.type === "web_field" && <small>{t("servers.custom_field_context", { name: integrations.find((i) => i.id === source.integrationId)?.name ?? "" })}</small>}</span><Icon name="chevron" size={13} />
    </button>
  </Dropdown>;
}
