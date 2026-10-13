import { t } from "../../i18n";
import type { WorkStatus } from "./api";

export const WORK_STATUSES: WorkStatus[] = ["READY", "BUSY", "BREAK", "UNAVAILABLE"];
const PATHS: Record<WorkStatus, string> = {
  READY: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM9 12l2 2 4-4",
  BUSY: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM8 12h8",
  BREAK: "M10 2v2M14 2v2M6 2v2M16 8a1 1 0 0 1 1 1v8a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1h14a4 4 0 1 1 0 8h-1",
  UNAVAILABLE: "M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z",
};
export function statusLabel(status: WorkStatus) {
  return t(`transfers.status_${status}`);
}
export function WorkStatusBadge({ status, compact = false }: { status: WorkStatus; compact?: boolean }) {
  return <span className={`work-status-badge is-${status.toLowerCase()}${compact ? " is-compact" : ""}`}>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={PATHS[status]} /></svg>{compact ? t(`transfers.short_${status}`) : statusLabel(status)}
  </span>;
}
