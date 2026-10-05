import { t } from "../../../i18n";
import { FormField, TextAreaField } from "../../../shared/form-controls";
import { Segmented } from "../../../shared/ui";
import { ServerHeaders } from "./ServerHeaders";
import { ServerEnabled, ServerErrors, ServerSaveActions } from "./ServerFormParts";
import { ServerWarning } from "./ServerWarning";
import type { ServerEditor } from "./useServerEditor";
import { TemplateAddressField } from "./TemplateAddressField";

export function HttpToolForm({ editor }: { editor: ServerEditor }) {
  const { draft, change, busy, errors } = editor;
  const server = draft.externalServer;
  const update = (next: Partial<typeof server>) => change({ ...draft, externalServer: { ...server, ...next } });
  return <div className="portal-settings-inner server-content">
    <div className="portal-settings-heading"><h3>{t("servers.tool")}</h3><p>{t("servers.http_lead")}</p></div>
    <div className="portal-settings-card server-form">
      <div className="server-two-fields">
        <div><FormField label={t("servers.display_name")} value={draft.name} error={errors.name?.join(" ")} disabled={busy} onChange={(name) => change({ ...draft, name })} /><small>{t("servers.display_name_hint")}</small></div>
        <div><FormField label={t("servers.tool_name")} value={server.toolName ?? ""} error={errors.toolName?.join(" ")} mono disabled={busy} onChange={(toolName) => update({ toolName })} /><small>{t("servers.tool_name_hint")}</small></div>
      </div>
      <div><TextAreaField label={t("servers.ai_description")} value={server.description} disabled={busy} onChange={(description) => update({ description })} />
        <small>{t("servers.ai_description_hint")}</small><ServerErrors messages={errors.description} /></div>
      <ServerEnabled editor={editor} />
    </div>
    <div className="portal-settings-card server-form">
      <strong>{t("servers.request")}</strong>
      <div>
        <label className="server-method-label">{t("servers.method_address")}</label>
        <div className="server-request-fields">
          <Segmented className="server-methods" value={server.method ?? "GET"} items={[["GET", "GET"], ["POST", "POST"]]}
            disabledKeys={busy ? ["GET", "POST"] : []} setValue={(method) => update({ method })} />
          <TemplateAddressField label={t("servers.request_url")} value={server.url} disabled={busy} invalid={Boolean(errors.url?.length)} onChange={(url) => update({ url })} />
        </div>
        <small>{t("servers.url_hint")}</small><ServerErrors messages={errors.url} />
        {server.method === "POST" && <label className="server-post-check"><input type="checkbox" checked={Boolean(server.readOnly)} disabled={busy}
          onChange={(event) => update({ readOnly: event.target.checked })} /><span><strong>{t("servers.post_read")}</strong><small>{t("servers.post_read_hint")}</small></span></label>}
      </div>
      <ServerHeaders headers={server.headers} onChange={(headers) => update({ headers })} disabled={busy} mcp={false} />
      <ServerErrors messages={errors.headers} />
      <ServerSaveActions editor={editor} />
    </div>
    <ServerWarning />
  </div>;
}
