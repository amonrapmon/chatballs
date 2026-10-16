import { t } from "../../i18n";
import { RuleJournalCard } from "./RuleJournalCard";

export function RuleJournalPage({ openConversation }: { openConversation: (id: number) => void }) {
  return <div className="settings-layout"><section className="settings-content is-single"><div className="settings-content-inner">
    <header className="settings-head"><div><h2>{t("handling_rules.journal_title")}</h2></div></header>
    <RuleJournalCard openConversation={openConversation} />
  </div></section></div>;
}
