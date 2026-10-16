import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { t } from "../../i18n";
import { SelectField } from "../../shared/form-controls";
import { fetchChannels, type ChannelOption, type Integration } from "./model";

export function ConnectionRouteFields({ initial, channelId, onChannel, groupId, onGroup }: {
  initial: Integration | null; channelId: string; onChannel: (id: string) => void;
  groupId: string; onGroup: (id: string) => void;
}) {
  const [agents, setAgents] = useState<ChannelOption[]>([]);
  const [groups, setGroups] = useState<Array<{ id: number; name: string }>>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([fetchChannels(), api<{ items: Array<{ id: number; name: string }> }>("/api/v1/company/groups/")])
      .then(([channels, response]) => { setAgents(channels); setGroups(response.items); })
      .catch((caught) => setError(caught instanceof Error ? caught.message : t("common.could_not_save")));
  }, []);
  const current = initial?.channel;
  const standalone = current && !current.hasAgent && String(current.id) === channelId;
  const shared = current?.shared && String(current.id) === channelId;
  const options: Array<[string, string]> = [["", t("settings.operator_connection")], ...agents.map((c): [string, string] => [String(c.id), c.name])];
  if (current && !agents.some((c) => c.id === current.id)) options.push([String(current.id), current.hasAgent ? current.name : t("settings.operator_connection")]);
  return <>
    <SelectField label={t("common.agent")} value={channelId} onChange={onChannel} options={options} />
    {(!channelId || standalone || shared) && <SelectField label={t("common.group")} value={groupId}
      disabled={Boolean(shared)} onChange={onGroup}
      options={[["", t("ai.without_group_conversations_visible_everyone")], ...groups.map((g): [string, string] => [String(g.id), g.name])]} />}
    {shared && <div className="integration-form-hint">{t("settings.connection_group_shared")}</div>}
    {error && <div className="integration-form-error">{error}</div>}
  </>;
}
