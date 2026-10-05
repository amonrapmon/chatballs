import { t } from "../../../i18n";
import { Icon } from "../../../shared/icons";
import { ContentState } from "../../../shared/ui";
import { Button } from "../../../shared/ui-controls";
import { serverHost } from "./model";
import type { ExternalServer } from "./types";

type ToolsState = NonNullable<ExternalServer["toolsState"]>;
export type ToolsErrorState = Extract<ToolsState, "unreachable" | "unauthorized" | "address_forbidden">;

export function isToolsError(state: ToolsState): state is ToolsErrorState {
  return state === "unreachable" || state === "unauthorized" || state === "address_forbidden";
}

export function McpToolsError({ state, url, busy, refresh, openConnection }: {
  state: ToolsErrorState; url: string; busy: boolean; refresh: () => void; openConnection: () => void;
}) {
  return <div className={`server-state-banner${state === "address_forbidden" ? " is-warning" : ""}`} role="alert">
    <Icon name={state === "unauthorized" ? "lock" : state === "address_forbidden" ? "shield" : "errorCircle"} size={18} />
    <div><strong>{t(`servers.${state}`)}</strong>
      <small>{t(state === "unauthorized" ? "servers.authorization_hint" : state === "address_forbidden" ? "servers.forbidden_hint" : "servers.unreachable_hint", { host: serverHost(url) })}</small>
      <Button variant="secondary" className="server-error-action" disabled={busy} onClick={state === "unreachable" ? refresh : openConnection}>
        {t(state === "unreachable" ? "servers.retry" : state === "address_forbidden" ? "servers.change_address" : "servers.open_connection")}
      </Button>
    </div>
  </div>;
}

export function McpToolsEmpty({ state, disabled, refresh }: { state: ToolsState; disabled: boolean; refresh: () => void }) {
  const forbidden = state === "address_forbidden";
  return <ContentState icon={<Icon name="wrench" size={18} />}
    title={t(state === "no_tools" ? "servers.no_tools" : forbidden ? "servers.forbidden_empty" : "servers.not_loaded")}
    text={t(state === "no_tools" ? "servers.no_tools_hint" : forbidden ? "servers.forbidden_empty_hint" : "servers.not_loaded_hint")}
    action={isToolsError(state) ? undefined : <Button variant="primary" disabled={disabled} onClick={refresh}>
      {t(state === "no_tools" ? "servers.refresh_empty" : "servers.load")}
    </Button>} />;
}

export function McpToolsLoading() {
  return <div className="server-tools-skeleton" aria-busy="true">
    <div className="server-tools-progress" role="status"><Icon name="refresh" size={14} />{t("servers.refreshing")}</div>
    {[[42, 70], [35, 58], [48, 64]].map(([title, description]) => <div className="server-tools-placeholder" key={title}>
      <i /><span><i style={{ width: `${title}%` }} /><i style={{ width: `${description}%` }} /></span>
    </div>)}
  </div>;
}
