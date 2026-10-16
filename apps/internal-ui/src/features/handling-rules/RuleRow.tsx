import { Switch } from "antd";
import { useEffect, useState } from "react";
import { fmt, t, tn } from "../../i18n";
import { Icon } from "../../shared/icons";
import type { AgentRef } from "../agents/model";
import { RuleFields } from "./RuleFields";
import { ruleName, ruleSummary } from "./model";
import type { HandlingRule, RuleErrors } from "./types";

export function RuleRow({ rule, channels, change, errors = {}, busy }: {
  rule: HandlingRule; channels: AgentRef[]; change: (rule: HandlingRule) => void; errors?: RuleErrors; busy: boolean;
}) {
  const [open, setOpen] = useState(rule.kind === "RECEIPT_CONFIRMATION" || rule.kind === "WAIT_EXCEEDED_NOTICE");
  const errorCount = Object.keys(errors).length;
  useEffect(() => { if (errorCount) setOpen(true); }, [errorCount]);
  const name = ruleName(rule.kind);
  return <section className={`handling-rule-row ${open ? "is-open" : ""} ${rule.enabled ? "" : "is-off"}`}>
    <header>
      <Switch aria-label={name} checked={rule.enabled} disabled={busy} onChange={enabled => change({ ...rule, enabled })} />
      <button className="handling-rule-expand" type="button" aria-expanded={open} title={t(`handling_rules.help_${rule.kind}`)} onClick={() => setOpen(!open)}>
        <span><strong>{name}{errorCount > 0 && <b className="handling-rule-error-badge">{tn("handling_rules.error_count", errorCount)}</b>}</strong>
          <small>{ruleSummary(rule)}</small></span>
        <small>{t("handling_rules.version", { version: fmt.number(rule.version) })}</small>
        <span className={`handling-rule-chevron ${open ? "is-open" : ""}`}><Icon name="chevron" size={15} /></span>
      </button>
    </header>
    {open && <RuleFields rule={rule} channels={channels} change={change} errors={errors} busy={busy} />}
  </section>;
}
