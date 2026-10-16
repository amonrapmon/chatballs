import { t } from "../../i18n";
import { Icon } from "../../shared/icons";

export function TransferAction({ onOpen }: { onOpen: () => void }) {
  return <button className="sales-secondary-action" onClick={onOpen}><Icon name="transfer" size={15} />{t("transfers.action")}</button>;
}
