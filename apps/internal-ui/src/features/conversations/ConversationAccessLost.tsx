import { Icon } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import { t } from "../../i18n";
import "./participants.css";

export function ConversationAccessLost({ detail, onBack }: { detail: string; onBack: () => void }) {
  return <section className="sales-conversation participant-access-lost" role="alert">
    <span><Icon name="lock" size={20} /></span><strong>{t("participants.lost_title")}</strong>
    <p>{detail}</p><Button variant="secondary" onClick={onBack}>{t("participants.back")}</Button>
  </section>;
}
