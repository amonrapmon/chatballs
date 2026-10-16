import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { fmt, t } from "../../i18n";
import { LoadingState } from "../../shared/ui";
import { Button } from "../../shared/ui-controls";
import type { PagedPayload } from "../../shared/usePagedResource";
import type { AgentRef } from "../agents/model";
import { ruleErrors, ruleKinds, ruleName } from "./model";
import { RuleRow } from "./RuleRow";
import { useRuleSettings } from "./useRuleSettings";
import "./settings.css";

export function RuleSettingsCard({ openJournal }: { openJournal: () => void }) {
  const state = useRuleSettings();
  const [channels, setChannels] = useState<AgentRef[]>([]);
  const [channelError, setChannelError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      const items: AgentRef[] = [];
      for (let page = 1; ; page++) {
        const response = await api<PagedPayload<AgentRef>>(`/api/v1/agents/?page=${page}`, { signal: controller.signal });
        items.push(...response.items);
        if (page >= response.pageCount) break;
      }
      if (!controller.signal.aborted) setChannels(items);
    }
    load().catch(problem => { if (!controller.signal.aborted) setChannelError(ruleErrors(problem).detail ?? ""); });
    return () => controller.abort();
  }, []);
  if (state.loading) return <LoadingState />;
  if (state.loadError) return <p role="alert">{state.loadError}</p>;
  const invalid = state.draft.find(rule => state.errors[rule.kind]);
  const latest = [...state.saved].filter(rule => rule.updatedAt).sort((a, b) => b.updatedAt!.localeCompare(a.updatedAt!))[0];
  return <section className="handling-rules-card">
    <header className="handling-rules-card-head"><div><h3>{t("handling_rules.rules")}</h3><p>{t("handling_rules.catalog_lead")}</p></div>
      <button className="link" type="button" onClick={openJournal}>{t("handling_rules.journal_title")}</button>
    </header>
    {channelError && <p className="handling-rule-error" role="alert">{channelError}</p>}
    {ruleKinds.map(kind => {
      const rule = state.draft.find(value => value.kind === kind);
      return rule && <RuleRow key={kind} rule={rule} channels={channels} change={state.change} busy={state.busy} errors={state.errors[kind]} />;
    })}
    <footer><small className={invalid ? "handling-rule-error" : ""} role={invalid ? "alert" : undefined}>
      {invalid ? t("handling_rules.unsaved", { rule: ruleName(invalid.kind) }) : <>
        {latest && t("settings.queue_saved_by", { when: fmt.shortDateTime(latest.updatedAt!), who: latest.updatedBy })}{" "}{t("handling_rules.version_help")}
      </>}
    </small><Button variant="primary" disabled={state.busy || !!channelError} onClick={() => void state.save()}>{t("common.save")}</Button></footer>
  </section>;
}
