import { t } from "../../i18n";
import { presenceNote, statusLabel, statusPresentation, statusSince, type WorkStatus, type WorkStatusCode } from "./model";
import "./styles.css";

// Две независимые характеристики сотрудника (кадры S1–S5): иконка с подписью —
// рабочий статус, круглая точка на фото — приложение открыто.

export function WorkStatusIcon({ code, size = 13 }: { code: WorkStatusCode; size?: number }) {
  const { stroke, path } = statusPresentation(code);
  return (
    <svg className="work-status-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

/** Иконка и подпись статуса; `time` дописывает «· с 09:12», если время сохранено. */
export function WorkStatusLabel({ value, time = false, short = true }: { value?: WorkStatus | null; time?: boolean; short?: boolean }) {
  if (!value) return <span className="work-status">—</span>;
  const since = time ? statusSince(value.changedAt) : "";
  return (
    <span className="work-status" style={{ color: statusPresentation(value.status).color }}>
      <WorkStatusIcon code={value.status} />
      <span>{statusLabel(value.status, short)}{since ? ` · ${since}` : ""}</span>
    </span>
  );
}

/** Ячейка справочника (кадр E1): под статусом — с какого времени он действует
 *  и присутствие, если оно со статусом расходится («с 13:30 · в приложении»). */
export function DirectoryWorkStatus({ value, online }: { value?: WorkStatus | null; online?: boolean }) {
  const since = value ? statusSince(value.changedAt) : "";
  const note = value && since ? presenceNote(value.status, Boolean(online)) : "";
  return (
    <span className="directory-work-status">
      <WorkStatusLabel value={value} short={false} />
      {since && <small>{note ? `${since} · ${note}` : since}</small>}
    </span>
  );
}

/** Точка присутствия на фото. `own` — своя точка: она гаснет при потере связи. */
export function PresenceDot({ online, own = false }: { online?: boolean; own?: boolean }) {
  if (online === undefined) return null;
  const title = online ? t("work_status.app_open") : t(own ? "work_status.no_connection" : "work_status.app_closed");
  return <i className={`presence-dot ${online ? "is-online" : ""}`} title={title} />;
}
