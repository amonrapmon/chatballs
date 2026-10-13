import { fmt, t } from "../../i18n";
import { Icon } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import type { SupervisionRevocation } from "./supervision";
import "./supervision.css";

export function SupervisionRevokedBanner({ loss, onBack }: { loss: SupervisionRevocation; onBack: () => void }) {
  return <div className="supervision-revoked-banner" role="alert">
    <Icon name="warning" size={18} />
    <div><strong>{t("supervision.lost_title", { group: loss.groupName })}</strong>
      <p>{t("supervision.lost_detail", { actor: loss.actorName, time: fmt.time(new Date(loss.occurredAt)) })}</p>
      <Button variant="secondary" onClick={onBack}>{t("supervision.back")}</Button>
    </div>
  </div>;
}
