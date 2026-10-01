import type { SiteField } from "@chatballs/contracts";
import type { CSSProperties } from "react";

import { fmt, t } from "../../../../i18n";
import { Icon } from "../../../../shared/icons";
import { CopyButton } from "../../../../shared/ui-controls";
import { ContextSection } from "../../../conversations/ContextSection";
import { isRecentSiteField, isSiteIdentifier, siteFieldHref } from "./siteData";
import { useSiteDataClock } from "./useSiteDataClock";
import "./site-data.css";

function SiteDataValue({ field }: { field: SiteField }) {
  if (field.type === "boolean" || field.type === "enum") {
    const style = field.type === "enum" && field.color
      ? { "--site-field-color": field.color } as CSSProperties : undefined;
    return <span className={`ctx-site-badge ${field.type === "boolean" ? (field.value ? "is-yes" : "is-no") : "is-enum"}`} style={style}>
      <i />{field.type === "boolean" ? t(field.value ? "site_fields.yes" : "site_fields.no") : field.display}
    </span>;
  }
  const href = siteFieldHref(field);
  const text = field.type === "datetime" ? fmt.shortDateTime(String(field.value))
    : field.type === "number" ? fmt.number(Number(field.value)) : field.display;
  return href
    ? <a className="link ctx-site-value" href={href} title={text} target={field.type === "url" ? "_blank" : undefined} rel={field.type === "url" ? "noopener noreferrer" : undefined}>{text}</a>
    : <span className={`ctx-site-value ${isSiteIdentifier(field) ? "is-mono" : ""} ${field.type === "number" || /(^|_)number($|_)/i.test(field.key) ? "is-number" : ""}`} title={text}>{text}</span>;
}

export function SiteDataSection({ fields }: { fields?: SiteField[] }) {
  const now = useSiteDataClock(fields);
  if (!fields?.length) return null;
  const updated = new Date(Math.max(...fields.map((field) => Date.parse(field.updatedAt))));
  return <ContextSection title={t("settings.site_data")} className="ctx-site-data" headerExtra={
    <span className="ctx-site-updated" title={t("site_fields.read_only")}>
      <Icon name="lock" size={12} />{t("site_fields.updated_at", { time: fmt.time(updated) })}
    </span>
  }>
    {fields.map((field) => {
      const recent = isRecentSiteField(field, now);
      const copy = isSiteIdentifier(field) || ["email", "phone", "url"].includes(field.type);
      return <div className={`ctx-site-row ${recent ? "is-recent" : ""}`} key={field.key}>
        <span className="ctx-site-label">{field.label}</span>
        <span className="ctx-site-content">
          <SiteDataValue field={field} />
          {recent && <small className="ctx-site-changed">{fmt.time(field.updatedAt)}</small>}
          {copy && <CopyButton className="ctx-site-copy" value={String(field.value)} />}
        </span>
      </div>;
    })}
  </ContextSection>;
}
