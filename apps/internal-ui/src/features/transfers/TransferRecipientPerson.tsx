import { t } from "../../i18n";
import { SmallAvatar } from "../conversations/assigneeOptions";
import { waitLabelOf, type ChatDirectoryEmployee } from "../conversations/model";

export function recipientPresence(person: ChatDirectoryEmployee) {
  return !person.assignmentAllowed ? t("transfers.status_forbidden") : person.online
    ? t("transfers.in_app") : person.lastSeenAt
      ? t("transfers.not_in_app_since", { time: waitLabelOf(person.lastSeenAt) }) : t("transfers.not_in_app");
}

export function TransferRecipientAvatar({ person }: { person: ChatDirectoryEmployee }) {
  return <span className={`transfer-person-avatar ${person.online ? "is-online" : "is-offline"}`}
    title={t(person.online ? "transfers.in_app" : "transfers.not_in_app")}>
    <SmallAvatar name={person.name} avatarUrl={person.avatarUrl} online={person.online} />
  </span>;
}
