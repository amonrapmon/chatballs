import { Dropdown } from "antd";

import { Icon } from "../../shared/icons";
import { t } from "../../i18n";
import { WorkStatusLabel } from "../work-status/WorkStatusLabel";
import { assigneeMenuItems, SmallAvatar } from "./assigneeOptions";
import type { EmployeeDirectory } from "./useEmployeeDirectory";
import type { ApiConversation } from "./model";
import { useAssigneeAvailability } from "./useAssigneeAvailability";

// Ответственный: присутствие на аватаре, рабочий статус справа (K1–K2).
export function DialogAssigneeField({ assignee, directory, viewerId, busy, canEdit, onPick }: {
  assignee: ApiConversation["assignedOperator"];
  directory: EmployeeDirectory;
  viewerId: number | null;
  busy: boolean;
  canEdit: boolean;
  onPick: (id: number | null) => void;
}) {
  const employee = useAssigneeAvailability(assignee, directory.employees);
  const assigneeHere = employee?.online;
  const assigneeStatus = employee?.workStatus;
  const assigneeLabel = assignee ? `${assignee.name}${viewerId === assignee.id ? t("common.you_suffix") : ""}` : t("conversations.unassigned");
  return (
    <>
      <label className="ctx-label">{t("common.assignee")}</label>
      <Dropdown
        disabled={!canEdit || busy || (directory.employees.length === 0 && !directory.query)}
        trigger={["click"]}
        overlayClassName="app-dropdown ctx-menu"
        menu={{
          items: assigneeMenuItems({
            directory,
            viewerId,
            assigneeId: assignee?.id,
            onPick,
          }),
        }}
      >
        <button type="button" className={`ctx-select ${assignee ? "" : "is-empty"}`}>
          {assignee ? <SmallAvatar name={assignee.name} avatarUrl={assignee.avatarUrl} online={assigneeHere} /> : <span className="ctx-avatar-empty" />}
          <span>{assigneeLabel}</span>
          {assigneeStatus && <WorkStatusLabel value={assigneeStatus} />}
          {canEdit && <Icon name="chevron" size={14} />}
        </button>
      </Dropdown>

    </>
  );
}
