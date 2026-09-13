import { expect, type Locator, type Page, test } from "@playwright/test";

const ORGANIZATION_PUBLIC_ID = "123e4567-e89b-12d3-a456-426614174000";
const SECOND_ORGANIZATION_PUBLIC_ID = "223e4567-e89b-12d3-a456-426614174000";

// Эти сценарии относятся только к internal-ui; на других проектах пропускаем.
test.beforeEach(({}, testInfo) => {
  test.skip(testInfo.project.name !== "internal-ui", "internal-ui only");
});

// Навигация владельца и администратора — ровно эти семь пунктов
// (SPEC-CHATBALLS-0031 §4). У сотрудника навигации нет вовсе: его единственный
// экран — чат.
const MANAGER_NAV = ["Чат", "Контакты", "Агенты", "Сотрудники", "Порталы", "База знаний", "Настройки"];

// Понятия, снесённые пивотом в контакт-центр (ADR-CHATBALLS-0041) и удалением
// сущности Product (ADR-CHATBALLS-0045). Проверяем, что они не вернулись в
// интерфейс: именно их ждали прежние редакции этих тестов.
const REMOVED_FROM_UI = ["Командный центр", "Отделы", "Продажи", "Каналы", "Подключения", "Продукты"];

// Состояние онбординга «Начало работы». По умолчанию сценарии получают
// пройденный визард — иначе он перекрывал бы проверяемый экран; тесты самого
// онбординга подставляют «ещё не открывал».
const ONBOARDING_STEPS_DONE = {
  providerConnected: true,
  agentActive: true,
  knowledgeFilled: true,
  connectionBound: true,
  widgetPublished: true,
  employeeInvited: true,
  platformConfigured: true,
  firstConversation: true,
};

type OnboardingMock = { steps: Record<string, boolean>; dismissedAt: string | null; completedAt: string | null };

const ONBOARDING_DISMISSED: OnboardingMock = {
  steps: ONBOARDING_STEPS_DONE,
  dismissedAt: "2026-01-01T00:00:00Z",
  completedAt: "2026-01-01T00:00:00Z",
};

// Человек в системе давно, но онбординга ещё не видел: признаков нет, часть
// шагов уже выполнена по факту.
const ONBOARDING_FRESH: OnboardingMock = {
  steps: { ...ONBOARDING_STEPS_DONE, widgetPublished: false, platformConfigured: false, firstConversation: false },
  dismissedAt: null,
  completedAt: null,
};

const GROUPS = [
  { id: 1, name: "Операторы", color: "#1677ff", memberCount: 1, memberIds: [7], createdAt: "2026-02-02T10:00:00Z" },
  { id: 2, name: "Поддержка", color: "#2aa876", memberCount: 0, memberIds: [], createdAt: "2026-02-02T10:00:00Z" },
];

type Role = "OWNER" | "ADMIN" | "EMPLOYEE";

// Права выводятся только из роли (ADR-CHATBALLS-0041 §5). Каталог — зеркало
// backend'а, `chatballs/identity/capabilities.py`: OWNER получает всё, ADMIN —
// всё, кроме передачи владения, EMPLOYEE — фиксированный набор для чата.
const OWNER_ONLY_CAPABILITIES = ["ownership.transfer"];
const EMPLOYEE_CAPABILITIES = [
  "conversations.view", "conversations.operate", "conversations.call",
  "customers.view", "support.view", "support.operate",
];
const ALL_CAPABILITIES = [
  "ai.manage", "ai.publish", "ai.view", "audit.view", "channels.manage", "channels.view",
  "company.manage", "company.view", "conversations.call", "conversations.operate",
  "conversations.view", "customers.manage", "customers.view", "employees.manage",
  "employees.manage_privileged", "employees.view", "groups.manage", "integrations.manage",
  "integrations.view", "notifications.manage", "ownership.transfer", "secrets.manage",
  "settings.manage", "settings.view", "support.operate", "support.view",
];

function capabilitiesFor(role: Role): string[] {
  if (role === "EMPLOYEE") return EMPLOYEE_CAPABILITIES;
  if (role === "ADMIN") return ALL_CAPABILITIES.filter((item) => !OWNER_ONLY_CAPABILITIES.includes(item));
  return ALL_CAPABILITIES;
}

function membershipFor(role: Role, overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    organizationPublicId: ORGANIZATION_PUBLIC_ID,
    organization: "atelier-nord",
    organizationName: "Ателье Норд",
    organizationLogoUrl: null,
    role,
    positionTitle: role === "EMPLOYEE" ? "Оператор" : "Владелец",
    totpRequired: false,
    capabilities: capabilitiesFor(role),
    groups: role === "EMPLOYEE" ? [{ id: 1, name: "Операторы" }] : [],
    joinedAt: "2026-02-02T10:00:00Z",
    ...overrides,
  };
}

function identityFor(role: Role, memberships = [membershipFor(role)]) {
  return {
    id: role === "EMPLOYEE" ? 7 : 1,
    email: role === "EMPLOYEE" ? "operator@example.com" : "owner@example.com",
    fullName: role === "EMPLOYEE" ? "Светлана Петрова" : "Елена Кузнецова",
    avatarUrl: null,
    mustChangePassword: false,
    totpEnabled: false,
    totpLastUsedAt: null,
    deliveryMode: "SELF_HOSTED",
    isInstanceAdmin: role === "OWNER",
    // Язык отдаёт сервер: без него интерфейс открылся бы на языке браузера.
    language: "ru",
    uiLanguage: "",
    memberships,
    uiTheme: "LIGHT",
    uiAccent: "#1677ff",
  };
}

const OWNER_IDENTITY = identityFor("OWNER");
// Администратор организации, но не установки: разделы и шаги про саму
// установку («Платформа», «Домен и почта») ему не показываются.
const ADMIN_IDENTITY = identityFor("ADMIN");
const EMPLOYEE_IDENTITY = identityFor("EMPLOYEE");

const EMPLOYEE_PERMISSIONS = {
  canView: true,
  canUpdateProfile: true,
  canChangeRole: true,
  canChangeGroups: true,
  canBlock: true,
  canUnblock: false,
  canResetPassword: true,
  canTerminateSessions: true,
  canTransferOwnership: false,
};

const STAFF = {
  id: 7,
  email: "s.petrova@example.com",
  fullName: "Светлана Петрова",
  avatarUrl: null,
  role: "EMPLOYEE",
  positionTitle: "Оператор",
  phone: "+7 903 118 77 51",
  groups: [{ id: 1, name: "Операторы" }],
  createdAt: "2026-05-20T10:00:00Z",
  lastLogin: "2026-09-01T08:30:00Z",
  isActive: true,
  isBlocked: false,
  mustChangePassword: false,
  totpRequired: false,
  totpEnabled: true,
  permissions: EMPLOYEE_PERMISSIONS,
};

// Администратор нужен списку кандидатов на передачу владения: без него диалог
// показывает пустое состояние, и проверять в нём нечего.
const ADMIN_STAFF = {
  ...STAFF,
  id: 4,
  email: "a.kim@example.com",
  fullName: "Анна Ким",
  role: "ADMIN",
  positionTitle: "Администратор",
  groups: [],
};

const OWNER_STAFF = {
  ...STAFF,
  id: 1,
  email: "owner@example.com",
  fullName: "Елена Кузнецова",
  role: "OWNER",
  positionTitle: "Владелец",
  groups: [],
  // Владельца нельзя удалить и заблокировать; единственное опасное действие на
  // его карточке — передача владения (SPEC-CHATBALLS-0031 §3).
  permissions: { ...EMPLOYEE_PERMISSIONS, canBlock: false, canChangeRole: false, canTransferOwnership: true },
};

// Пустое, но валидное окружение экрана: чат, справочники и чек-лист запуска.
// Без него любой экран падает в состояние ошибки и проверять на нём нечего.
// Ожидающее приглашение существующей учётной записи: строка со статусом
// «Приглашён» перед сотрудниками (кадры E1/E2).
const INVITATION = {
  id: 9,
  email: "guest@example.com",
  fullName: "Пётр Приглашённый",
  avatarUrl: null,
  role: "EMPLOYEE",
  positionTitle: "Оператор поддержки",
  phone: "",
  groups: [{ id: 1, name: "Операторы" }],
  invitedAt: "2026-09-10T10:00:00Z",
  expiresAt: "2026-09-17T10:00:00Z",
};

async function mockInstance(page: Page, onboarding: OnboardingMock = ONBOARDING_DISMISSED, onboardingActions: string[] = []) {
  await page.route("**/api/v1/setup/", (route) => route.fulfill({ json: { needsSetup: false } }));
  await page.route("**/api/v1/instance/**", (route) => route.fulfill({ json: {} }));
  await page.route("**/api/v1/organizations/*/conversations/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/conversations/counters/")) {
      return route.fulfill({ json: { all: 0, waiting: 0, mine: 0, ungrouped: 0, groups: [], agents: [], assignees: [] } });
    }
    if (path.endsWith("/conversations/directory/")) {
      return route.fulfill({ json: { groups: GROUPS.map((group) => ({ id: group.id, name: group.name, color: group.color })), employees: [] } });
    }
    if (path.endsWith("/conversations/stats/")) return route.fulfill({ json: { waiting: 0 } });
    return route.fulfill({ json: { items: [] } });
  });
  await page.route("**/api/v1/organizations/*/company/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/company/onboarding/")) {
      if (route.request().method() === "POST") {
        const action = JSON.parse(route.request().postData() ?? "{}").action;
        onboardingActions.push(action);
        const now = "2026-03-01T10:00:00Z";
        return route.fulfill({
          json: {
            steps: onboarding.steps,
            dismissedAt: action === "restart" ? null : now,
            completedAt: action === "complete" ? now : null,
          },
        });
      }
      return route.fulfill({ json: onboarding });
    }
    return route.fulfill({ json: { items: GROUPS } });
  });
  await page.route("**/api/v1/organizations/*/agents/**", (route) => route.fulfill({ json: { items: [], page: 1, pageSize: 20, total: 0, pageCount: 1 } }));
  await page.route("**/api/v1/organizations/*/notifications/**", (route) => route.fulfill({ json: { items: [] } }));
}

async function mockEmployees(page: Page) {
  await page.route("**/api/v1/organizations/*/employees/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const detail = path.match(/\/employees\/(\d+)\/$/);
    if (detail) {
      const employee = { "1": OWNER_STAFF, "4": ADMIN_STAFF }[detail[1]] ?? STAFF;
      return route.fulfill({
        json: {
          employee: {
            ...employee,
            activeSessionCount: 1,
            passwordChangedAt: "2026-08-01T10:00:00Z",
            auditEvents: [{ action: "identity.employee_created", result: "SUCCESS", createdAt: "2026-05-20T10:00:00Z" }],
          },
        },
      });
    }
    // Список сотрудников постраничный, роль и поиск отбирает сервер — мок
    // повторяет этот контракт, иначе он проверял бы несуществующее поведение.
    const params = new URL(route.request().url()).searchParams;
    const role = params.get("role");
    const query = (params.get("q") ?? "").toLowerCase();
    const items = [OWNER_STAFF, ADMIN_STAFF, STAFF]
      .filter((employee) => !role || employee.role === role)
      .filter((employee) => !query || `${employee.fullName} ${employee.email} ${employee.positionTitle}`.toLowerCase().includes(query));
    return route.fulfill({
      json: { items, page: 1, pageSize: 20, total: items.length, pageCount: 1, invitations: [INVITATION] },
    });
  });
}

async function mockSession(page: Page, user: object | null) {
  await page.route("**/api/v1/auth/session/", (route) =>
    route.fulfill({ json: user ? { authenticated: true, user } : { authenticated: false, language: "ru" } }),
  );
}

async function login(page: Page, user: object, onboarding: OnboardingMock = ONBOARDING_DISMISSED, onboardingActions: string[] = []) {
  await mockSession(page, null);
  await mockInstance(page, onboarding, onboardingActions);
  await mockEmployees(page);
  await page.route("**/api/v1/auth/login/", (route) => route.fulfill({ json: { authenticated: true, user } }));
  await page.goto("/");
  await page.getByPlaceholder("you@domain.ru").fill("user@example.com");
  await page.getByPlaceholder("Пароль").fill("Password-123");
  await page.getByRole("button", { name: "Войти" }).click();
}

const managerNav = (page: Page) => page.locator("nav.hub-nav button.hub-nav-item");

test("владелец после входа попадает в чат и видит семь пунктов навигации", async ({ page }) => {
  await login(page, OWNER_IDENTITY);

  await expect(page).toHaveURL(new RegExp(`/organizations/${ORGANIZATION_PUBLIC_ID}/chat`));
  await expect(managerNav(page)).toHaveCount(MANAGER_NAV.length);
  for (const label of MANAGER_NAV) {
    await expect(page.locator("nav.hub-nav").getByRole("button", { name: label, exact: true })).toBeVisible();
  }
  for (const removed of REMOVED_FROM_UI) {
    await expect(page.getByRole("button", { name: removed, exact: true })).toHaveCount(0);
  }
});

test("сотрудник после входа попадает в чат, и навигации у него нет", async ({ page }) => {
  await login(page, EMPLOYEE_IDENTITY);

  await expect(page).toHaveURL(new RegExp(`/organizations/${ORGANIZATION_PUBLIC_ID}/chat`));
  await expect(page.locator(".sales-conversation-empty")).toBeVisible();
  // Единственный экран сотрудника: сайдбар сведён к дереву диалогов, пунктов
  // администрирования нет ни одного. Дерево тоже лежит в nav.hub-nav, поэтому
  // проверяем именно пункты навигации.
  await expect(page.locator("nav.chat-scope-tree")).toBeVisible();
  await expect(managerNav(page)).toHaveCount(0);
  for (const label of MANAGER_NAV.filter((item) => item !== "Чат")) {
    await expect(page.getByRole("button", { name: label, exact: true })).toHaveCount(0);
  }
});

test("сотрудник на менеджерском маршруте видит экран 403", async ({ page }) => {
  await mockSession(page, EMPLOYEE_IDENTITY);
  await mockInstance(page);
  await mockEmployees(page);

  await page.goto("/employees");

  await expect(page.getByText("403 · Доступ запрещён")).toBeVisible();
  await expect(page.getByRole("button", { name: "Вернуться" })).toBeVisible();
});

test("организация выбирается адресом, а не сохранённой сессией", async ({ page }) => {
  const secondMembership = membershipFor("OWNER", {
    id: 3,
    organizationPublicId: SECOND_ORGANIZATION_PUBLIC_ID,
    organization: "second",
    organizationName: "Вторая организация",
  });
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/v1/organizations/")) requests.push(request.url());
  });
  await mockInstance(page);
  await mockEmployees(page);
  await mockSession(page, identityFor("OWNER", [membershipFor("OWNER"), secondMembership]));

  await page.goto(`/organizations/${SECOND_ORGANIZATION_PUBLIC_ID}/`);

  await expect(managerNav(page)).toHaveCount(MANAGER_NAV.length);
  // Организация берётся из адреса: запросы уходят только во вторую организацию,
  // хотя членство в первой тоже есть.
  await expect.poll(() => requests.some((url) => url.includes(SECOND_ORGANIZATION_PUBLIC_ID))).toBe(true);
  expect(requests.filter((url) => url.includes(ORGANIZATION_PUBLIC_ID))).toEqual([]);
});

test("ожидающее приглашение показано строкой «Приглашён» с меню отправки и отзыва", async ({ page }) => {
  await mockSession(page, OWNER_IDENTITY);
  await mockInstance(page);
  await mockEmployees(page);
  const posted: string[] = [];
  await page.route("**/api/v1/organizations/*/employees/invitations/**", (route) => {
    posted.push(new URL(route.request().url()).pathname);
    return route.fulfill({ json: { ok: true } });
  });

  await page.goto(`/organizations/${ORGANIZATION_PUBLIC_ID}/employees`);

  const row = page.locator(".employees-row.is-invited");
  await expect(row).toHaveCount(1);
  await expect(row.getByText("Пётр Приглашённый")).toBeVisible();
  await expect(row.locator(".employees-badge.has-dot")).toHaveText("Приглашён");
  await expect(row.getByText("Оператор поддержки")).toBeVisible();

  await row.locator(".employees-row-menu").click();
  await page.getByRole("button", { name: "Отправить приглашение ещё раз" }).click();
  await expect.poll(() => posted).toContain(`/api/v1/organizations/${ORGANIZATION_PUBLIC_ID}/employees/invitations/9/resend/`);
});

test("гость по ссылке-приглашению задаёт имя и пароль и попадает в организацию", async ({ page }) => {
  await mockSession(page, null);
  await mockInstance(page);
  await mockEmployees(page);
  await page.route("**/api/v1/auth/invitations/preview/**", (route) =>
    route.fulfill({ json: { valid: true, email: "new-owner@example.com", organizationName: "Новая организация", accountExists: false } }),
  );
  const registered: string[] = [];
  await page.route("**/api/v1/auth/invitations/register/", async (route) => {
    registered.push(route.request().postData() ?? "");
    const user = identityFor("OWNER", [membershipFor("OWNER", { organizationPublicId: SECOND_ORGANIZATION_PUBLIC_ID, organization: "new", organizationName: "Новая организация" })]);
    // После регистрации сессия уже есть — сессионный мок отвечает как для вошедшего.
    await mockSession(page, user);
    return route.fulfill({ status: 201, json: { authenticated: true, user, organizationPublicId: SECOND_ORGANIZATION_PUBLIC_ID } });
  });

  await page.goto("/join?token=guest-token");

  await expect(page.getByText("Вас приглашают в «Новая организация»")).toBeVisible();
  await page.getByPlaceholder("Елена Кузнецова").fill("Новый Владелец");
  await page.getByPlaceholder("Минимум 10 символов").fill("Very-strong-passphrase-42");
  await page.getByRole("button", { name: "Принять приглашение" }).click();

  await expect(page).toHaveURL(new RegExp(`/organizations/${SECOND_ORGANIZATION_PUBLIC_ID}/`));
  await expect(managerNav(page)).toHaveCount(MANAGER_NAV.length);
  expect(registered[0]).toContain("guest-token");
});

test("администратор установки видит баннер о новой версии и запускает обновление", async ({ page }) => {
  await mockSession(page, OWNER_IDENTITY);
  await mockInstance(page);
  await mockEmployees(page);
  const update = {
    currentVersion: "1.4.0", latestVersion: "1.5.0", latestName: "v1.5.0", latestNotes: "", latestPublishedAt: null,
    latestPageUrl: "https://github.com/dartdavros/chatballs/releases/tag/v1.5.0", available: true, checkedAt: null,
    checkError: "", updaterOnline: true, install: { version: null, status: "IDLE", message: "", requestedAt: null, updatedAt: null },
  };
  await page.route("**/api/v1/instance/update/", (route) => route.fulfill({ json: { update } }));
  const installs: string[] = [];
  await page.route("**/api/v1/instance/update/install/", (route) => {
    installs.push(route.request().method());
    return route.fulfill({ status: 202, json: { update: { ...update, install: { ...update.install, version: "1.5.0", status: "REQUESTED" } } } });
  });

  await page.goto(`/organizations/${ORGANIZATION_PUBLIC_ID}/chat`);

  const banner = page.locator(".update-banner");
  await expect(banner).toContainText("Доступна версия 1.5.0");
  await banner.getByRole("button", { name: "Обновить", exact: true }).click();
  await expect(page.getByText("Обновить до 1.5.0?")).toBeVisible();
  await page.locator(".decision-dialog").getByRole("button", { name: "Обновить", exact: true }).click();

  await expect.poll(() => installs).toEqual(["POST"]);
  await expect(page.locator(".update-banner")).toContainText("Обновление до 1.5.0");
});

test("с несколькими организациями вход открывает первую, переключатель ведёт во вторую", async ({ page }) => {
  const secondMembership = membershipFor("OWNER", {
    id: 3,
    organizationPublicId: SECOND_ORGANIZATION_PUBLIC_ID,
    organization: "second",
    organizationName: "Вторая организация",
  });
  await mockInstance(page);
  await mockEmployees(page);
  await mockSession(page, identityFor("OWNER", [membershipFor("OWNER"), secondMembership]));

  // Адрес без организации: открывается первая по списку, а не экран «нет доступа».
  await page.goto("/");

  await expect(managerNav(page)).toHaveCount(MANAGER_NAV.length);
  await expect(page).toHaveURL(new RegExp(`/organizations/${ORGANIZATION_PUBLIC_ID}/`));
  await expect(page.locator(".hub-brand-switch span")).toHaveText("Ателье Норд");

  // Переключатель (A1): в списке обе организации, текущая отмечена.
  await page.locator(".hub-brand-switch").click();
  const menu = page.locator(".app-dropdown");
  await expect(menu.getByRole("button", { name: "Ателье Норд" })).toHaveClass(/is-checked/);
  await menu.getByRole("button", { name: "Вторая организация" }).click();

  await expect(page).toHaveURL(new RegExp(`/organizations/${SECOND_ORGANIZATION_PUBLIC_ID}/`));
  await expect(page.locator(".hub-brand-switch span")).toHaveText("Вторая организация");
  await expect(managerNav(page)).toHaveCount(MANAGER_NAV.length);
});

test("после входа с несколькими организациями показывается выбор, ссылка на организацию его минует", async ({ page }) => {
  const secondMembership = membershipFor("OWNER", {
    id: 3,
    organizationPublicId: SECOND_ORGANIZATION_PUBLIC_ID,
    organization: "second",
    organizationName: "Вторая организация",
    positionTitle: "Директор",
  });
  const identity = identityFor("OWNER", [membershipFor("OWNER"), secondMembership]);
  await login(page, identity);

  // Экран выбора: обе организации строками с ролью, приложение ещё не открыто.
  await expect(page.getByRole("heading", { name: "Выберите организацию" })).toBeVisible();
  const list = page.locator(".auth-org-list");
  await expect(list.getByRole("button")).toHaveCount(2);
  await expect(list.getByRole("button", { name: /Вторая организация/ })).toContainText("Директор");
  await expect(managerNav(page)).toHaveCount(0);

  await list.getByRole("button", { name: /Вторая организация/ }).click();

  await expect(page).toHaveURL(new RegExp(`/organizations/${SECOND_ORGANIZATION_PUBLIC_ID}/chat`));
  await expect(page.locator(".hub-brand-switch span")).toHaveText("Вторая организация");
  await expect(managerNav(page)).toHaveCount(MANAGER_NAV.length);

  // Прямая ссылка на организацию: вход ведёт сразу в неё (на стартовый
  // экран, как и всегда после входа), без выбора.
  await mockSession(page, null);
  await page.goto(`/organizations/${ORGANIZATION_PUBLIC_ID}/employees`);
  await page.getByPlaceholder("you@domain.ru").fill("user@example.com");
  await page.getByPlaceholder("Пароль").fill("Password-123");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page).toHaveURL(new RegExp(`/organizations/${ORGANIZATION_PUBLIC_ID}/chat`));
  await expect(page.locator(".hub-brand-switch span")).toHaveText("Ателье Норд");
  await expect(page.getByRole("heading", { name: "Выберите организацию" })).toHaveCount(0);
});

test("владелец добавляет организацию из переключателя и сразу в неё попадает", async ({ page }) => {
  const NEW_ORGANIZATION_PUBLIC_ID = "323e4567-e89b-12d3-a456-426614174000";
  await mockInstance(page);
  await mockEmployees(page);
  await mockSession(page, OWNER_IDENTITY);
  await page.route("**/api/v1/organizations/options/", (route) =>
    route.fulfill({ json: { timezones: ["Europe/Moscow", "Europe/Berlin"], languages: [{ code: "ru", label: "Русский" }, { code: "en", label: "English" }], currencies: ["RUB"] } }),
  );
  let created: Record<string, unknown> | null = null;
  await page.route("**/api/v1/organizations/", (route) => {
    created = route.request().postDataJSON();
    const membership = membershipFor("OWNER", {
      id: 9,
      organizationPublicId: NEW_ORGANIZATION_PUBLIC_ID,
      organization: "vtoraya",
      organizationName: "Вторая компания",
    });
    return route.fulfill({
      status: 201,
      json: { user: identityFor("OWNER", [membershipFor("OWNER"), membership]), organizationPublicId: NEW_ORGANIZATION_PUBLIC_ID },
    });
  });

  await page.goto("/");
  await expect(managerNav(page)).toHaveCount(MANAGER_NAV.length);

  // В переключателе (A1) под списком организаций — «Добавить организацию».
  await page.locator(".hub-brand-switch").click();
  await page.locator(".app-dropdown").getByRole("button", { name: "Добавить организацию" }).click();
  await expect(page).toHaveURL(/\/organizations\/new$/);
  await expect(page.getByRole("heading", { name: "Новая организация" })).toBeVisible();

  await page.getByPlaceholder("Например, «Ателье Норд»").fill("Вторая компания");
  // Язык интерфейса — селект приложения, как часовой пояс.
  await page.getByRole("button", { name: "Язык интерфейса" }).click();
  await page.locator(".app-dropdown.is-field .ant-dropdown-menu-item", { hasText: "English" }).click();
  await page.getByRole("button", { name: "Создать организацию" }).click();

  // Сразу в новой организации: адрес и переключатель показывают её.
  await expect(page).toHaveURL(new RegExp(`/organizations/${NEW_ORGANIZATION_PUBLIC_ID}/chat`));
  await expect(page.locator(".hub-brand-switch span")).toHaveText("Вторая компания");
  // Валюты в теле нет: выбора её в интерфейсе больше нет, сервер ставит сам.
  expect(created).toEqual({ name: "Вторая компания", timezone: "Europe/Moscow", language: "en" });
});

test("сотрудник без прав менеджера не видит «Добавить организацию»", async ({ page }) => {
  await mockInstance(page);
  await mockEmployees(page);
  await mockSession(page, identityFor("EMPLOYEE"));

  await page.goto("/");
  await page.locator(".hub-brand-switch").click();

  const menu = page.locator(".app-dropdown");
  await expect(menu.getByRole("button", { name: "Ателье Норд" })).toBeVisible();
  await expect(menu.getByRole("button", { name: "Добавить организацию" })).toHaveCount(0);
});

test("интерфейс работает на минимальной поддерживаемой ширине 1024px", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await mockInstance(page);
  await mockEmployees(page);
  await mockSession(page, OWNER_IDENTITY);

  await page.goto("/");

  await expect(managerNav(page)).toHaveCount(MANAGER_NAV.length);
  await expect(page.locator(".sales-conversation-empty")).toBeVisible();
  // На минимальной ширине страница не должна прокручиваться по горизонтали
  // (SPEC-CHATBALLS-0031 §8).
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({ path: "test-results/internal-ui-owner-1024.png" });
});

test("экран сотрудников: список, создание, карточка и передача владения", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 940 });
  await mockInstance(page);
  await mockEmployees(page);
  await mockSession(page, OWNER_IDENTITY);

  await page.goto("/employees");
  await expect(page.getByRole("heading", { name: "Сотрудники" })).toBeVisible();
  await expect(page.getByText("Светлана Петрова").first()).toBeVisible();

  // Состав колонок текущего списка. Прежняя редакция теста искала колонку
  // «ДОСТУП» ролью columnheader — список не является семантической таблицей.
  const head = page.locator(".employees-thead");
  for (const column of ["Сотрудник", "Роль", "Должность", "Группы", "Доступ", "Статус", "Последний вход"]) {
    await expect(head.getByText(column, { exact: true })).toBeVisible();
  }
  await page.screenshot({ path: "test-results/employees-list.png", fullPage: true });

  await page.getByRole("button", { name: "Добавить сотрудника" }).click();
  await expect(page.getByRole("complementary", { name: "Новый сотрудник" })).toBeVisible();
  await page.screenshot({ path: "test-results/employees-create.png", fullPage: true });
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();

  // Карточка сотрудника: должность и группы вместо прежних профилей доступа и
  // отделов.
  await page.getByRole("button", { name: /Светлана Петрова/ }).first().click();
  await expect(page).toHaveURL(/\/employees\/7$/);
  await expect(page.getByRole("heading", { name: "Светлана Петрова" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Должность и группы" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Системная роль" })).toBeVisible();
  await expect(page.getByText("Профили доступа")).toHaveCount(0);
  await page.screenshot({ path: "test-results/employees-detail.png", fullPage: true });

  // Передача владения живёт в «Опасной зоне» карточки владельца, а не в меню
  // строки списка.
  await page.getByRole("button", { name: "Все сотрудники" }).click();
  await page.getByRole("button", { name: /Елена Кузнецова/ }).first().click();
  await expect(page).toHaveURL(/\/employees\/1$/);
  await expect(page.getByRole("heading", { name: "Опасная зона" })).toBeVisible();
  await page.getByRole("button", { name: "Передать владение" }).click();
  const transferDialog = page.getByRole("dialog", { name: "Передача владения" });
  await expect(transferDialog).toBeVisible();
  // Кандидатами могут быть только активные администраторы: сотрудника в списке
  // быть не должно.
  await transferDialog.getByRole("button", { name: "Новый владелец" }).click();
  const candidates = page.locator(".app-dropdown.is-field .ant-dropdown-menu-item");
  await expect(candidates).toHaveCount(1);
  await expect(candidates).toContainText("Анна Ким");
  await page.keyboard.press("Escape");
  await page.screenshot({ path: "test-results/employees-ownership.png", fullPage: true });
  await transferDialog.getByRole("button", { name: "Отмена" }).click();
  await expect(transferDialog).toHaveCount(0);
});

// Онбординг «Начало работы» (дизайн-базлайн, handoff 2026-09-13). Требование
// заказчика: визард показывается владельцу и администратору, пока он его не
// закроет, — в том числе тем, кто работает в установке давно. Поэтому признак
// «закрыл» живёт на сервере, а не в localStorage, и мок отдаёт его пустым.

/** Ждёт конца ob-rise: до него карточка полупрозрачна и снимок выходит блёклым. */
const settled = (locator: Locator) => expect(locator).toHaveCSS("opacity", "1");

test("онбординг открывается владельцу, который его ещё не закрывал", async ({ page }) => {
  const actions: string[] = [];
  await login(page, OWNER_IDENTITY, ONBOARDING_FRESH, actions);

  const welcome = page.locator(".ob-welcome");
  await expect(welcome).toBeVisible();
  // Число в заголовке — словом, как в макете, а не цифрой.
  await expect(welcome.getByRole("heading")).toHaveText("Восемь шагов до первого ответа клиенту");
  // Карточка выезжает 320ms: снимок до конца анимации ловит полупрозрачность.
  await settled(welcome);
  await page.screenshot({ path: "test-results/onboarding-welcome.png" });

  await welcome.getByRole("button", { name: "Начать настройку" }).click();
  const wizard = page.locator(".ob-steps");
  await expect(wizard).toBeVisible();
  // Владелец здесь ещё и администратор установки — значит все восемь шагов.
  await expect(wizard.locator(".ob-rail-step")).toHaveCount(8);
  await expect(wizard.locator(".ob-chip.is-accent")).toContainText("Шаг 1 из 8");
  await expect(wizard.getByRole("heading")).toHaveText("Подключите AI-провайдера");
  // Прогресс приходит фактами с сервера, а не нажатиями «Далее».
  await expect(wizard.locator(".ob-rail-progress-row span")).toHaveText("Готово 5 из 8");
  await settled(wizard);
  await page.screenshot({ path: "test-results/onboarding-steps.png" });

  await wizard.getByRole("button", { name: "Далее" }).click();
  await expect(wizard.getByRole("heading")).toHaveText("Создайте AI-агента");
  await wizard.getByRole("button", { name: "Назад" }).click();
  await expect(wizard.getByRole("heading")).toHaveText("Подключите AI-провайдера");

  // «Закрыть и настроить самому» записывает отказ на сервер, а не в браузер.
  await wizard.getByRole("button", { name: "Закрыть и настроить самому" }).click();
  await expect(wizard).toHaveCount(0);
  await expect.poll(() => actions).toEqual(["dismiss"]);

  // Закрытый визард оставляет пилюлю возврата: настроено ещё не всё.
  const launcher = page.locator(".ob-launcher");
  await expect(launcher).toBeVisible();
  await expect(launcher).toContainText("5/8");
  await page.screenshot({ path: "test-results/onboarding-launcher.png" });
});

test("администратору организации шаг про домен и почту не показывают", async ({ page }) => {
  await login(page, ADMIN_IDENTITY, ONBOARDING_FRESH);

  await page.locator(".ob-welcome").getByRole("button", { name: "Начать настройку" }).click();
  const wizard = page.locator(".ob-steps");
  // Раздел «Платформа» — свойство установки, а не организации: шагов семь, и
  // счётчик считает от семи.
  await expect(wizard.locator(".ob-rail-step")).toHaveCount(7);
  await expect(wizard.locator(".ob-rail-step")).not.toContainText(["Домен и почта"]);
  await expect(wizard.locator(".ob-rail-progress-row span")).toHaveText("Готово 5 из 7");
  await expect(page.locator(".ob-steps")).toBeVisible();
});

test("у семи шагов заголовок приветствия тоже числом-словом", async ({ page }) => {
  await login(page, ADMIN_IDENTITY, ONBOARDING_FRESH);

  await expect(page.locator(".ob-welcome").getByRole("heading")).toHaveText("Семь шагов до первого ответа клиенту");
});

test("«Показать где» затемняет приложение и подсвечивает пункт сайдбара", async ({ page }) => {
  await login(page, OWNER_IDENTITY, ONBOARDING_FRESH);

  const wizard = page.locator(".ob-steps");
  await page.locator(".ob-welcome").getByRole("button", { name: "Начать настройку" }).click();
  // Второй шаг рассказывает про «Агентов» — их пункт тур и подсвечивает.
  await wizard.getByRole("button", { name: "Далее" }).click();
  await wizard.getByRole("button", { name: "Показать где" }).click();

  await expect(wizard).toHaveCount(0);
  const callout = page.locator(".ob-tour-callout");
  await expect(callout).toBeVisible();
  await expect(callout).toContainText("Раздел «Агенты»");
  await expect(page.locator(".ob-tour-dim")).toHaveCount(4);
  await settled(callout);
  await page.screenshot({ path: "test-results/onboarding-tour.png" });

  await callout.getByRole("button", { name: "Понятно, к шагам" }).click();
  await expect(page.locator(".ob-tour-callout")).toHaveCount(0);
  await expect(wizard.getByRole("heading")).toHaveText("Создайте AI-агента");
});

test("закрытый онбординг открывается заново ссылкой внизу субменю «Настроек»", async ({ page }) => {
  await login(page, OWNER_IDENTITY, ONBOARDING_DISMISSED);

  // Визард закрыт и всё настроено: ни окна, ни пилюли.
  await expect(page.locator(".ob-overlay")).toHaveCount(0);
  await expect(page.locator(".ob-launcher")).toHaveCount(0);

  // Переход внутри приложения: перезагрузка страницы вернула бы форму входа —
  // сессия в моках живёт только до неё.
  await page.locator("nav.hub-nav").getByRole("button", { name: "Настройки", exact: true }).click();
  const link = page.locator(".settings-subnav-onboarding");
  await expect(link).toBeVisible();
  await expect(link).toContainText("Начало работы");
  await page.screenshot({ path: "test-results/onboarding-settings-link.png" });

  await link.click();
  await expect(page.locator(".ob-steps")).toBeVisible();
});

test("сотрудник онбординга не видит", async ({ page }) => {
  await login(page, EMPLOYEE_IDENTITY, ONBOARDING_FRESH);

  await expect(page.locator(".ob-overlay")).toHaveCount(0);
  await expect(page.locator(".ob-launcher")).toHaveCount(0);
});

test("последний шаг ведёт на финальный экран и записывает «пройден»", async ({ page }) => {
  const actions: string[] = [];
  await login(page, OWNER_IDENTITY, ONBOARDING_FRESH, actions);

  const wizard = page.locator(".ob-steps");
  await page.locator(".ob-welcome").getByRole("button", { name: "Начать настройку" }).click();
  // Навигация по рейке свободная: до последнего шага можно дойти одним кликом.
  await wizard.locator(".ob-rail-step").last().click();
  await expect(wizard.getByRole("heading")).toHaveText("Напишите боту как клиент");

  await wizard.getByRole("button", { name: "Завершить" }).click();
  const done = page.locator(".ob-done");
  await expect(done.getByRole("heading")).toHaveText("Всё готово — можно принимать клиентов");
  // Сводка честно показывает, что три шага так и не выполнены по факту.
  await expect(done.locator(".ob-summary-item")).toHaveCount(8);
  await expect(done.locator(".ob-summary-item.is-done")).toHaveCount(5);
  await settled(done);
  await page.screenshot({ path: "test-results/onboarding-done.png" });

  await done.getByRole("button", { name: "Перейти в чат" }).click();
  await expect(page.locator(".ob-overlay")).toHaveCount(0);
  await expect(page).toHaveURL(/\/chat$/);
  await expect.poll(() => actions).toEqual(["complete"]);
});

test("подсветка тура встаёт ровно по элементу после смены экрана", async ({ page }) => {
  await login(page, OWNER_IDENTITY, ONBOARDING_FRESH);

  const wizard = page.locator(".ob-steps");
  await page.locator(".ob-welcome").getByRole("button", { name: "Начать настройку" }).click();
  // Первый шаг ведёт в «Настройки → AI-провайдер». Новый маршрут въезжает
  // анимацией `surface-enter` (translateY 6px): замер на первом кадре поставил
  // бы рамку на 6px мимо строки, поэтому тур доводит его до остановки.
  await wizard.getByRole("button", { name: "Показать где" }).click();

  const callout = page.locator(".ob-tour-callout");
  await expect(callout).toContainText("Настройки → AI-провайдер");
  await settled(callout);

  const geometry = await page.evaluate(() => {
    const box = (selector: string) => {
      const rect = document.querySelector(selector)!.getBoundingClientRect();
      return [Math.round(rect.x), Math.round(rect.y), Math.round(rect.width), Math.round(rect.height)];
    };
    const root = box(".hub-shell");
    const target = box('[data-onboarding-target="settings-ai"]');
    const dim = [...document.querySelectorAll(".ob-tour-dim")].map((el) => {
      const rect = el.getBoundingClientRect();
      return [Math.round(rect.x), Math.round(rect.y), Math.round(rect.width), Math.round(rect.height)];
    });
    return { root, target, spot: box(".ob-tour-spot"), dim };
  });

  const [x, y, w, h] = geometry.target;
  const [, , rootW, rootH] = geometry.root;
  // Рамка — цель с отступом 6px со всех сторон.
  expect(geometry.spot).toEqual([x - 6, y - 6, w + 12, h + 12]);
  // Четыре затемнения смыкаются вокруг неё, не оставляя ни щели, ни просвета.
  expect(geometry.dim).toEqual([
    [0, 0, rootW, y - 6],
    [0, y + h + 6, rootW, rootH - (y + h + 6)],
    [0, y - 6, x - 6, h + 12],
    [x + w + 6, y - 6, rootW - (x + w + 6), h + 12],
  ]);

  await page.screenshot({ path: "test-results/onboarding-tour-settings.png" });
});

test("свёрнутый список диалогов возвращается и без выбранного диалога", async ({ page }) => {
  await login(page, OWNER_IDENTITY);
  await expect(page).toHaveURL(/\/chat$/);

  // Кнопка возврата жила только в шапке переписки, а при пустом списке
  // переписки нет — список оказывался не вернуть.
  await page.getByRole("button", { name: "Скрыть список" }).click();
  await expect(page.locator(".sales-dialogs.is-list-collapsed")).toBeVisible();
  await expect(page.locator(".sales-dialog-list")).toBeHidden();

  await page.getByRole("button", { name: "Показать список" }).click();
  await expect(page.locator(".sales-dialogs.is-list-collapsed")).toHaveCount(0);
  await expect(page.locator(".sales-dialog-list")).toBeVisible();
});
