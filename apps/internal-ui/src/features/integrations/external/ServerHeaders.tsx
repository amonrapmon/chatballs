import { t } from "../../../i18n";
import { FormField } from "../../../shared/form-controls";
import { Icon } from "../../../shared/icons";
import { Button, IconButton } from "../../../shared/ui-controls";
import type { ServerHeader } from "./types";

export function ServerHeaders({ headers, onChange, disabled, mcp }: {
  headers: ServerHeader[]; onChange: (headers: ServerHeader[]) => void; disabled: boolean; mcp: boolean;
}) {
  return <div className="server-headers">
    <strong>{t(mcp ? "servers.auth_headers" : "servers.headers")}</strong>
    <small>{t(mcp ? "servers.headers_hint" : "servers.http_headers_hint")}</small>
    {headers.map((header, index) => <HeaderRow key={index} header={header} disabled={disabled}
      onChange={(next) => onChange(headers.map((h, i) => i === index ? next : h))}
      onDelete={() => onChange(headers.filter((_, i) => i !== index))} />)}
    <Button variant="secondary" className="server-add-header" icon="plus" disabled={disabled || headers.length >= 10}
      onClick={() => onChange([...headers, { name: "", value: "", secret: true }])}>{t("servers.header")}</Button>
  </div>;
}

function HeaderRow({ header, onChange, onDelete, disabled }: {
  header: ServerHeader; onChange: (header: ServerHeader) => void; onDelete: () => void; disabled: boolean;
}) {
  return <div className="server-header-row">
    <FormField label={t("servers.header_name")} value={header.name} mono disabled={disabled}
      onChange={(name) => onChange({ ...header, name, saved: name === header.name && header.saved })} />
    {header.secret && header.saved ? <div className="server-secret-saved">
      <Icon name="lock" size={13} /><code>••••••••••••</code><small>{t("servers.saved")}</small>
      <button className="link" type="button" disabled={disabled} onClick={() => onChange({ ...header, saved: false, value: "" })}>{t("servers.replace")}</button>
    </div> : <div className="server-header-value">
      <FormField label={t("servers.header_value")} type={header.secret ? "password" : "text"} mono value={header.value}
        disabled={disabled} onChange={(value) => onChange({ ...header, value })} />
    </div>}
    <IconButton icon="trash" label={t("servers.delete_header")} disabled={disabled} onClick={onDelete} />
  </div>;
}
