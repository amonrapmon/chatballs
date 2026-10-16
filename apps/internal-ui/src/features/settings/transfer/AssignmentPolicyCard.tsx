import { Switch } from "antd";
import { useEffect, useRef, useState } from "react";
import { t } from "../../../i18n";
import { LoadingState } from "../../../shared/ui";
import { errorText, fetchPolicy, savePolicy, type AssignmentPolicy, type WorkStatus } from "../../transfers/api";
import { WORK_STATUSES, statusLabel, WorkStatusBadge } from "../../transfers/WorkStatusBadge";

export function AssignmentPolicyCard() {
  const [policy, setPolicy] = useState<AssignmentPolicy | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const attempted = useRef<AssignmentPolicy | null>(null);
  useEffect(() => {
    let active = true;
    fetchPolicy().then((response) => {
      if (active) {
        setPolicy(response.allowedStatuses);
        if (!response.allowedStatuses) setError(t("settings.could_not_load_settings"));
      }
    })
      .catch((problem) => { if (active) setError(errorText(problem)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  async function save(next: AssignmentPolicy) {
    attempted.current = next; setBusy(true); setError("");
    try { setPolicy((await savePolicy(next)).allowedStatuses); }
    catch (problem) { setError(errorText(problem)); }
    finally { setBusy(false); }
  }
  function toggle(status: WorkStatus, checked: boolean) {
    if (policy) void save({ ...policy, [status]: checked });
  }
  return <section className="transfer-settings-card">
    <header><h3>{t("transfers.policy_title")}</h3><p>{t("transfers.policy_lead")}</p></header>
    <div className="transfer-policy-row is-heading"><span>{t("transfers.status")}</span><span>{t("transfers.label")}</span><span>{t("transfers.assign_allowed")}</span></div>
    {loading && <LoadingState />}
    {policy && WORK_STATUSES.map((status) => <div className="transfer-policy-row" key={status}>
      <div><strong>{statusLabel(status)}</strong>{status === "BUSY" && <small>{t("transfers.busy_hint")}</small>}</div>
      <WorkStatusBadge status={status} compact />
      <Switch size="small" aria-label={statusLabel(status)} checked={policy[status]} disabled={busy} onChange={(checked) => toggle(status, checked)} />
    </div>)}
    {error ? <p className="transfer-settings-note transfer-error">{error} {attempted.current && <button className="link" onClick={() => void save(attempted.current!)} disabled={busy}>{t("common.try_again")}</button>}</p>
      : <p className="transfer-settings-note">{t("transfers.policy_note")}</p>}
  </section>;
}
