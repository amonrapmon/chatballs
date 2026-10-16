import { useState } from "react";
import { t } from "../../i18n";
import { FilterDropdown, SearchInput } from "../../shared/ui-controls";
import { AUDIT_PERIODS, type AuditPeriod } from "../administration/model";
import { ruleKinds, ruleName } from "./model";
import type { DisplayStatus, JournalFilters as Filters } from "./journalModel";
import type { RuleKind } from "./types";

export function JournalFilters({ filters, change }: { filters: Filters; change: (filters: Filters) => void }) {
  const [open, setOpen] = useState("");
  const choices = [
    { key: "kind", caption: t("handling_rules.rule_filter"), label: filters.kind ? ruleName(filters.kind) : t("handling_rules.all_rules"),
      options: [{ value: "", label: t("handling_rules.all_rules") }, ...ruleKinds.map(kind => ({ value: kind, label: ruleName(kind) }))] },
    { key: "status", caption: t("handling_rules.result"), label: filters.status ? t(`handling_rules.status_${filters.status}`) : t("common.all"),
      options: [{ value: "", label: t("common.all") }, ...(["PENDING", "EXECUTED", "CANCELLED", "SKIPPED", "FAILED"] as DisplayStatus[]).map(status => ({ value: status, label: t(`handling_rules.status_${status}`) }))] },
    { key: "period", caption: t("admin.period"), label: AUDIT_PERIODS.find(([key]) => key === filters.period)![1],
      options: AUDIT_PERIODS.map(([value, label]) => ({ value, label })) },
  ];
  return <div className="handling-journal-filters">
    {choices.map(choice => <label key={choice.key}><span>{choice.caption}</span>
      <FilterDropdown label={choice.label} options={choice.options} selected={choice.key === "period" && filters.period === "today" ? [] : filters[choice.key as "kind" | "status" | "period"] ? [filters[choice.key as "kind" | "status" | "period"]] : []}
        open={open === choice.key} onOpenChange={show => setOpen(show ? choice.key : "")}
        onSelect={value => change({ ...filters, [choice.key]: value as RuleKind | DisplayStatus | AuditPeriod })} />
    </label>)}
    <div className="handling-journal-spacer" />
    <SearchInput placeholder={t("handling_rules.search")} value={filters.search} onChange={search => change({ ...filters, search })} />
  </div>;
}
