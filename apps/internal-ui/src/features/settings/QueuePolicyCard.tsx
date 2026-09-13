import { useEffect, useState } from "react";

import { Icon } from "../../shared/icons";
import { Button } from "../../shared/ui-controls";
import { fmt, t } from "../../i18n";
import {
  QUEUE_POLICY_FIELDS,
  fetchQueuePolicy,
  saveQueuePolicy,
  type QueuePolicy,
  type QueuePolicyField,
} from "./queuePolicy";

// Раздел «Когда звать на помощь» (макет «Очередь и уведомления», кадр Q2).
// Сроки действуют на всю организацию и считаются с момента, когда диалог встал
// в очередь. Правит их тот, кто управляет настройками; остальным сервер
// отвечает отказом, поэтому карточка просто не покажется.

type Draft = Record<QueuePolicyField, string>;

const draftOf = (policy: QueuePolicy): Draft =>
  Object.fromEntries(QUEUE_POLICY_FIELDS.map(({ key }) => [key, String(policy[key])])) as Draft;

export function QueuePolicyCard({ canManage }: { canManage: boolean }) {
  const [policy, setPolicy] = useState<QueuePolicy | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchQueuePolicy()
      .then((loaded) => {
        setPolicy(loaded);
        setDraft(draftOf(loaded));
      })
      .catch(() => setError(t("settings.queue_policy_unavailable")));
  }, []);

  async function save(values: Partial<Record<QueuePolicyField, number>>) {
    setBusy(true);
    setError("");
    try {
      const saved = await saveQueuePolicy(values);
      setPolicy(saved);
      setDraft(draftOf(saved));
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : t("settings.queue_policy_unavailable"));
    } finally {
      setBusy(false);
    }
  }

  if (error && !policy) return <p className="settings-note">{error}</p>;
  if (!policy || !draft) return null;

  const changed = QUEUE_POLICY_FIELDS.some(({ key }) => draft[key] !== String(policy[key]));
  const isDefault = QUEUE_POLICY_FIELDS.every(({ key }) => policy[key] === policy.defaults[key]);

  return (
    <>
      <div className="queue-policy-card">
        {QUEUE_POLICY_FIELDS.map(({ key, title, hint }) => (
          <div className="queue-policy-row" key={key}>
            <div>
              <strong>{title}</strong>
              <small>{hint}</small>
            </div>
            <label className="queue-policy-value">
              <input
                type="number"
                min={1}
                max={1440}
                value={draft[key]}
                disabled={!canManage || busy}
                onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}
                aria-label={title}
              />
              <span>{t("settings.queue_minutes_unit")}</span>
            </label>
          </div>
        ))}
        <div className="queue-policy-footer">
          <small>
            {policy.updatedAt
              ? t("settings.queue_saved_by", {
                  when: `${fmt.shortDate(new Date(policy.updatedAt))}, ${fmt.time(new Date(policy.updatedAt))}`,
                  who: policy.updatedBy,
                })
              : t("settings.queue_never_changed")}
          </small>
          {canManage && (
            <div className="queue-policy-actions">
              <Button
                variant="secondary"
                disabled={busy || isDefault}
                onClick={() => void save(policy.defaults)}
              >
                {t("settings.queue_restore_defaults")}
              </Button>
              <Button
                variant="primary"
                disabled={busy || !changed}
                onClick={() =>
                  void save(
                    Object.fromEntries(
                      QUEUE_POLICY_FIELDS.map(({ key }) => [key, Number(draft[key])]),
                    ) as Record<QueuePolicyField, number>,
                  )
                }
              >
                {t("common.save")}
              </Button>
            </div>
          )}
        </div>
      </div>
      {error && <p className="settings-note">{error}</p>}
      <div className="queue-policy-warning">
        <span><Icon name="alert" size={16} strokeWidth={2} /></span>
        <p>{t("settings.queue_delivery_warning")}</p>
      </div>
    </>
  );
}
