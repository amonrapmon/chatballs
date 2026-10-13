import { setCurrentLanguage } from "@chatballs/shared";
import { beforeEach, describe, expect, it } from "vitest";

import type { Employee } from "../../types";
import { employeeForm, groupsLabel, roleAccessLabel } from "./model";

beforeEach(() => { setCurrentLanguage("ru"); });

const baseEmployee: Employee = {
  id: 1,
  email: "employee@example.test",
  fullName: "Анна Котова",
  role: "EMPLOYEE",
  positionTitle: "Оператор",
  phone: "",
  groups: [{ id: 10, name: "Операторы" }],
  isActive: true,
  isBlocked: false,
  mustChangePassword: false,
  totpRequired: false,
  totpEnabled: false,
};

describe("employee list model", () => {
  it("keeps ordinary membership separate from the supervisor control area", () => {
    const supervisor = { ...baseEmployee, role: "SUPERVISOR" as const, supervisedGroups: [{ id: 20, name: "Support" }] };
    expect(employeeForm(supervisor).groupIds).toEqual([10]);
    expect(employeeForm(supervisor).supervisedGroupIds).toEqual([20]);
    expect(employeeForm(supervisor).role).toBe("SUPERVISOR");
    expect(employeeForm({ ...supervisor, supervisedGroups: [] }).supervisedGroupIds).toEqual([]);
  });
  it("labels groups and role-based access", () => {
    expect(groupsLabel(baseEmployee)).toBe("Операторы");
    expect(groupsLabel({ ...baseEmployee, groups: [] })).toBe("Без группы");
    expect(roleAccessLabel(baseEmployee)).toBe("Только чат");
    expect(roleAccessLabel({ ...baseEmployee, role: "ADMIN" })).toBe("Полный доступ");
    expect(roleAccessLabel({ ...baseEmployee, role: "OWNER" })).toBe("Полный доступ");
  });
});
