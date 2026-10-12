import { useEffect, useState } from "react";

import { t } from "../../i18n";
import { SwitchButton } from "../../shared/form-controls";
import type { Employee } from "../../types";
import { setTemplateGrant, templateGrant } from "../reply-templates/api";

// Блок «Разрешения» карточки сотрудника (platform-expansion, кадры E2–E4):
// отдельное право управлять общими шаблонами ответов, не меняющее роль.
// Владелец и администратор управляют общими шаблонами по роли — им блок не
// нужен. Сервер отдаёт состояние только тому, кто вправе его менять.

export function EmployeePermissionsCard({ employee }: { employee: Employee }) {
  const byRole = employee.role === "OWNER" || employee.role === "ADMIN";
  const membershipId = byRole ? undefined : employee.membershipId;
  const [granted, setGranted] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setGranted(null);
    setError("");
    if (membershipId === undefined) return undefined;
    let active = true;
    templateGrant(membershipId)
      .then((grant) => { if (active) setGranted(grant.granted); })
      .catch(() => { /* Нет права выдавать разрешение — блок не показывается. */ });
    return () => { active = false; };
  }, [membershipId]);

  if (membershipId === undefined || granted === null) return null;

  async function toggle() {
    if (membershipId === undefined || granted === null || saving) return;
    const next = !granted;
    setSaving(true);
    setError("");
    setGranted(next);
    try {
      setGranted((await setTemplateGrant(membershipId, next)).granted);
    } catch (caught) {
      // Переключатель возвращается в прежнее положение, причина — в блоке.
      setGranted(!next);
      setError(caught instanceof Error ? caught.message : t("common.could_not_complete_action"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="employee-card is-rail">
      <h3>{t("templates.permissions_title")}</h3>
      <p>{t("templates.permissions_lead")}</p>
      <div className="employee-security-row is-last">
        <div>
          <strong>{t("templates.manage_shared")}</strong>
          <small>{t("templates.manage_shared_help")}</small>
        </div>
        <SwitchButton checked={granted} className="ui-switch is-large" label={t("templates.manage_shared")} disabled={saving} onClick={() => void toggle()} />
      </div>
      {error && <small className="form-field-error" role="alert">{error}</small>}
    </section>
  );
}
