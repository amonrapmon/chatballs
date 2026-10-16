import { useState } from "react";
import { fmt, t } from "../../i18n";
import { LoadingState } from "../../shared/ui";
import { JournalFilters } from "./JournalFilters";
import { JournalRows } from "./JournalRows";
import { emptyFilters, filterJournal, type JournalFilters as Filters } from "./journalModel";
import { useRuleJournal } from "./useRuleJournal";
import "./journal.css";

export function RuleJournalCard({ openConversation }: { openConversation: (id: number) => void }) {
  const state = useRuleJournal();
  const [filters, setFilters] = useState(emptyFilters);
  const entries = state.timezone ? filterJournal(state.entries, filters, state.timezone, state.names) : [];
  function change(value: Filters) { setFilters(value); }
  if (state.loading) return <LoadingState />;
  if (state.error) return <p role="alert">{state.error}</p>;
  return <section className="handling-journal-card">
    <header><h3>{t("handling_rules.journal")}</h3><p>{t("handling_rules.journal_lead")}</p></header>
    <JournalFilters filters={filters} change={change} />
    <JournalRows entries={entries} names={state.names} timezone={state.timezone} openConversation={openConversation} />
    {!entries.length && <p className="handling-journal-empty">
      {filters.period === "today" ? t(filters.status === "FAILED" ? "handling_rules.errors_empty_today" : "handling_rules.empty_today") : t("admin.no_events_yet_2")}{" "}
      <button className="link" type="button" onClick={() => change({ ...emptyFilters, period: "all" })}>{t("handling_rules.reset_filter")}</button>
    </p>}
    {!!entries.length && <p className="handling-journal-note">{t("handling_rules.shown", { count: fmt.number(entries.length), total: fmt.number(state.entries.length) })}</p>}
  </section>;
}
