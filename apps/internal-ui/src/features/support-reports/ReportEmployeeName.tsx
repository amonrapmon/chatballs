import { Avatar } from "../../shared/ui";
import type { Employee } from "../../types";
import { PresenceDot } from "../work-status/WorkStatusLabel";
import { employeeAvatarColor } from "../employees/model";
import type { ReportEmployee } from "./types";

export function ReportEmployeeName({ row, employee, presence = false }: { row: ReportEmployee; employee?: Employee; presence?: boolean }) {
  return <span className="report-employee-name">
    {employee && <span className="report-avatar"><Avatar employee={employee} background={employeeAvatarColor(employee)} />{presence && <PresenceDot online={employee.online} />}</span>}
    <strong>{row.name}</strong>
  </span>;
}
