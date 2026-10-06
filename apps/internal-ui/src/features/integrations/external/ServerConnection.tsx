import { t } from "../../../i18n";
import { FormField, TextAreaField } from "../../../shared/form-controls";
import { ServerHeaders } from "./ServerHeaders";
import { ServerEnabled, ServerErrors, ServerSaveActions } from "./ServerFormParts";
import { ServerWarning } from "./ServerWarning";
import type { ServerEditor } from "./useServerEditor";

export function ServerConnection({ editor }: { editor: ServerEditor }) {
  const { draft, change, busy, errors } = editor;
  const server = draft.externalServer;
  const update = (next: Partial<typeof server>) => change({ ...draft, externalServer: { ...server, ...next } });
  return <div className="portal-settings-inner server-content server-mcp-content">
    <div className="portal-settings-heading"><h3>{t("servers.connection")}</h3><p>{t("servers.connection_lead")}</p></div>
    <ServerEnabled editor={editor} />
    <div className="portal-settings-card server-form">
      <FormField label={t("servers.name")} value={draft.name} disabled={busy} error={errors.name?.join(" ")}
        onChange={(name) => change({ ...draft, name })} />
      <div><TextAreaField label={t("servers.description")} value={server.description} disabled={busy} onChange={(description) => update({ description })} />
        <small>{t("servers.description_hint")}</small></div>
      <div><FormField label={t("servers.address")} value={server.url} mono disabled={busy} onChange={(url) => update({ url })} />
        <small>{t("servers.address_hint")}</small><ServerErrors messages={errors.url} /></div>
      <ServerHeaders headers={server.headers} onChange={(headers) => update({ headers })} disabled={busy} mcp />
      <ServerErrors messages={errors.headers} />
      <ServerSaveActions editor={editor} mcp />
    </div>
    <ServerWarning />
  </div>;
}
