import { Dropdown } from "antd";
import { t } from "../../../i18n";
import { SelectField, SwitchButton, TextAreaField } from "../../../shared/form-controls";
import { Icon } from "../../../shared/icons";
import type { Integration } from "../model";
import { ParameterSourceSelect } from "./ParameterSourceSelect";
import type { ToolParameter } from "./types";

export function ParameterRow({ parameter, integrations, disabled, method, inPath, first, last, onChange, onAction }: {
  parameter: ToolParameter; integrations: Integration[]; disabled: boolean; method: string; inPath: boolean; first: boolean; last: boolean;
  onChange: (parameter: ToolParameter) => void; onAction: (key: string) => void;
}) {
  const bound = parameter.source.type !== "ai";
  return <div className="server-parameter-row">
    <button className="link is-mono is-neutral" type="button" onClick={() => onAction("open")}>{parameter.name}</button>
    <SelectField label={`${parameter.name}: ${t("servers.parameter_type")}`} value={parameter.type} disabled={disabled}
      options={[["string", t("servers.type_string")], ["number", t("servers.type_number")], ["boolean", t("servers.type_boolean")]]}
      onChange={(type) => onChange({ ...parameter, type: type as ToolParameter["type"] })} />
    <SwitchButton className="ui-switch is-compact" label={`${parameter.name}: ${t("servers.parameter_required")}`}
      checked={parameter.required || inPath} disabled={disabled || inPath} onClick={() => onChange({ ...parameter, required: !parameter.required })} />
    <SelectField label={`${parameter.name}: ${t("servers.parameter_location")}`} value={inPath ? "path" : parameter.location} disabled={disabled || inPath}
      options={[["path", t("servers.path")], ["query", t("servers.query")], ...(method === "POST" ? [["body", t("servers.body")] as [string, string]] : [])]}
      onChange={(location) => onChange({ ...parameter, location: location as ToolParameter["location"] })} />
    <ParameterSourceSelect label={`${parameter.name}: ${t("servers.parameter_source")}`} source={parameter.source} integrations={integrations} disabled={disabled}
      onChange={(source) => onChange({ ...parameter, source })} />
    <Dropdown trigger={["click"]} overlayClassName="app-dropdown" menu={{ onClick: ({ key }) => onAction(key), items: [
      { key: "open", label: t("servers.open_parameter"), disabled },
      { key: "duplicate", label: t("servers.duplicate"), disabled },
      { key: "up", label: t("servers.move_up"), disabled: disabled || first },
      { key: "down", label: t("servers.move_down"), disabled: disabled || last },
      { type: "divider" }, { key: "delete", label: t("common.delete"), danger: true, disabled },
    ] }}><button className="row-menu-button" type="button" aria-label={`${parameter.name}: ${t("settings.integration_actions")}`}><Icon name="more" /></button></Dropdown>
    <div className="server-parameter-description"><TextAreaField label={t("servers.ai_description")} value={bound ? t("servers.bound_description") : parameter.description}
      disabled={disabled || bound} onChange={(description) => onChange({ ...parameter, description })} /></div>
  </div>;
}
