import { useState } from "react";
import { fmt, t, tn } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { Button } from "../../../shared/ui-controls";
import type { Integration } from "../model";
import { blankParameter, duplicateParameter, moveParameter } from "./model";
import { ParameterDrawer } from "./ParameterDrawer";
import { ParameterRow } from "./ParameterRow";
import { RequestPreview } from "./RequestPreview";
import { ServerErrors } from "./ServerFormParts";
import { placeholders } from "./validation";
import type { ToolParameter } from "./types";
import type { ServerEditor } from "./useServerEditor";

export function HttpParameters({ editor, integrations }: { editor: ServerEditor; integrations: Integration[] }) {
  const [editing, setEditing] = useState<{ index: number; initial: ToolParameter } | null>(null);
  const server = editor.draft.externalServer;
  const parameters = server.parameters ?? [];
  const ai = parameters.filter((p) => p.source.type === "ai").length;
  const update = (next: ToolParameter[]) => editor.change({ ...editor.draft, externalServer: { ...server, parameters: next } });
  function action(index: number, key: string) {
    if (key === "open") setEditing({ index, initial: parameters[index] });
    if (key === "duplicate" && parameters.length < 20) update(duplicateParameter(parameters, index));
    if (key === "up" || key === "down") update(moveParameter(parameters, index, key === "up" ? -1 : 1));
    if (key === "delete") update(parameters.filter((_, i) => i !== index));
  }
  return <div className="portal-settings-inner server-content server-parameters-content">
    <div className="portal-settings-heading"><h3>{t("servers.parameters")}</h3><p>{t("servers.parameters_lead")}</p></div>
    <div className="server-tools-card">
      <div className="server-tools-summary"><div><strong>{tn("servers.parameter_count", parameters.length)}</strong><small>{t("servers.parameter_sources", { system: fmt.number(parameters.length - ai), ai: fmt.number(ai) })}</small></div>
        <Button variant="primary" icon="plus" disabled={editor.busy || parameters.length >= 20} onClick={() => setEditing({ index: parameters.length, initial: blankParameter() })}>{t("servers.add_parameter")}</Button></div>
      <div className="server-parameters-scroll">
        <div className="server-parameter-head">{["parameter_name", "parameter_type", "parameter_required", "parameter_location", "parameter_source"].map((key) => <span key={key}>{t(`servers.${key as "parameter_name"}`)}</span>)}<span /></div>
        {parameters.map((parameter, index) => <ParameterRow key={index} parameter={parameter} integrations={integrations} disabled={editor.busy}
          selected={editing?.index === index}
          method={server.method ?? "GET"} inPath={placeholders(server.url).includes(parameter.name)} first={index === 0} last={index === parameters.length - 1}
          onChange={(next) => update(parameters.map((p, i) => i === index ? next : p))} onAction={(key) => action(index, key)} />)}
      </div>
      <div className="server-card-note"><small><Icon name="lock" size={13} />{t("servers.bound_hint")}</small><small><Icon name="message" size={13} />{t("servers.web_hint")}</small></div>
    </div>
    <ServerErrors messages={editor.errors.parameters} />
    <RequestPreview server={server} integrations={integrations} />
    {editing && <ParameterDrawer key={editing.index} initial={editing.initial} index={editing.index} name={editor.draft.name} server={server} integrations={integrations}
      onClose={() => setEditing(null)} onDelete={() => { update(parameters.filter((_, i) => i !== editing.index)); setEditing(null); }}
      onSave={(parameter) => { const next = [...parameters]; next[editing.index] = parameter; update(next); setEditing(null); }} />}
  </div>;
}
