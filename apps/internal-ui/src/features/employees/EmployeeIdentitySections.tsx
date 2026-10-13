import type { Employee, EmployeeGroup, Role } from "../../types";
import { Icon } from "../../shared/icons";
import { EmployeeGroupPicks } from "./EmployeeGroupPicks";
import { EmployeeSupervisionCard } from "./EmployeeSupervisionCard";
import type { EmployeeForm } from "./model";
import { t } from "../../i18n";

// Основные данные · Должность и группы · Системная роль (кадры E3/E4).
// Владельцу все роли закрыты: роль владельца меняется только передачей владения.

const ROLE_OPTIONS: Array<{ role: Role; label: string; description: string }> = [
  { role: "OWNER", label: t("common.owner"), description: t("admin.full_access_exactly_one_per") },
  { role: "ADMIN", label: t("common.administrator"), description: t("admin.full_access_identical_owner_owner") },
  { role: "EMPLOYEE", label: t("common.operator"), description: t("admin.works_chat_sees_conversations_their") },
  { role: "SUPERVISOR", label: t("supervision.role"), description: t("supervision.role_help") },
];

export function EmployeeIdentitySections({ groups, employee, form, updateForm }: {
  groups: EmployeeGroup[];
  employee: Employee;
  form: EmployeeForm;
  updateForm: (field: keyof EmployeeForm, value: string | boolean | number[]) => void;
}) {
  const canProfile = employee.permissions?.canUpdateProfile ?? false;
  const canGroups = employee.permissions?.canChangeGroups ?? false;
  const canRole = employee.permissions?.canChangeRole ?? false;
  const isOwner = employee.role === "OWNER";

  return (
    <>
      <section className="employee-card">
        <h3>{t("admin.main_details")}</h3>
        <div className="employee-field-grid">
          <EmployeeField label={t("common.name")} value={form.fullName} readOnly={!canProfile} onChange={(value) => updateForm("fullName", value)} />
          <EmployeeField label={t("common.phone")} value={form.phone} readOnly={!canProfile} onChange={(value) => updateForm("phone", value)} />
          <EmployeeField className="is-wide" label={t("profile.email_used_sign")} value={form.email} readOnly={!canProfile} mono onChange={(value) => updateForm("email", value)} />
        </div>
      </section>

      <section className="employee-card">
        <h3>{t("admin.position_groups")}</h3>
        <p>{t("admin.group_decides_which_conversations_visible")}</p>
        <EmployeeField className="is-single" label={t("common.position")} value={form.positionTitle} readOnly={!canProfile} placeholder={t("admin.e_g_operator")} onChange={(value) => updateForm("positionTitle", value)} />
        {groups.length > 0 ? (
          <EmployeeGroupPicks groups={groups} selected={form.groupIds} disabled={!canGroups} onChange={(ids) => updateForm("groupIds", ids)} />
        ) : (
          <p className="employee-create-note">{t("admin.there_no_groups_yet_so_2")}</p>
        )}
      </section>

      {!isOwner && <EmployeeSupervisionCard employee={employee} groups={groups} form={form} onChange={(ids) => updateForm("supervisedGroupIds", ids)} />}
      <section className="employee-card">
        <h3>{t("admin.system_role")}</h3>
        <p>{isOwner ? t("admin.owner_s_role_changes_only") : t("supervision.role_lead")}</p>
        <div className="employee-choice-list">
          {ROLE_OPTIONS.map((option) => {
            const active = form.role === option.role;
            // Владельца нельзя выбрать ролью: единственный путь — передача владения.
            const locked = isOwner || !canRole || option.role === "OWNER";
            return (
              <button
                className={`employee-choice ${active ? "is-on" : ""} ${locked ? "is-locked" : ""}`}
                type="button"
                disabled={locked}
                onClick={() => updateForm("role", option.role)}
                key={option.role}
              >
                <i>{active && <span />}</i>
                <span>
                  <strong>{option.label}{locked && <Icon name="lock" size={12} strokeWidth={1.8} />}</strong>
                  <small>{option.description}</small>
                </span>
              </button>
            );
          })}
        </div>
      </section>
    </>
  );
}

function EmployeeField({ className = "", label, mono = false, onChange, placeholder = "", readOnly, value }: {
  className?: string;
  label: string;
  mono?: boolean;
  onChange: (value: string) => void;
  placeholder?: string;
  readOnly: boolean;
  value: string;
}) {
  return (
    <label className={`employee-field ${className} ${readOnly ? "is-readonly" : ""}`}>
      <span>{label}</span>
      <input className={mono ? "mono" : ""} value={value} placeholder={placeholder} readOnly={readOnly} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
