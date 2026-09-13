import { expect, test, type Page } from "@playwright/test";

// Страница профиля: карточка уведомлений со строкой «Браузер» и устойчивость
// страницы к неполному ответу соседней карточки.
//
// Разрешение браузера в тестах подменяется: выдать его сайт не может, а
// состояние иначе зависело бы от того, что headless-Chromium ответит сегодня.

const ORGANIZATION_PUBLIC_ID = "123e4567-e89b-12d3-a456-426614174000";

const OWNER = {
  id: 1,
  email: "owner@example.com",
  fullName: "Елена Кузнецова",
  avatarUrl: null,
  mustChangePassword: false,
  totpEnabled: false,
  totpLastUsedAt: null,
  deliveryMode: "SELF_HOSTED",
  isInstanceAdmin: true,
  language: "ru",
  uiLanguage: "",
  uiTheme: "LIGHT",
  uiAccent: "#1677ff",
  memberships: [
    {
      id: 1,
      organizationPublicId: ORGANIZATION_PUBLIC_ID,
      organization: "atelier-nord",
      organizationName: "Ателье Норд",
      organizationLogoUrl: null,
      role: "OWNER",
      positionTitle: "Владелец",
      totpRequired: false,
      capabilities: ["company.view", "conversations.view", "employees.manage_privileged", "settings.view"],
      groups: [],
      joinedAt: "2026-02-02T10:00:00Z",
    },
  ],
};

const TYPES = [
  { code: "DIALOG_WAITING", label: "Диалог ждёт оператора" },
  { code: "DIALOG_NEW_MESSAGE", label: "Новое сообщение в диалоге" },
];

// Сценарий дважды загружает SPA (вход формой, затем адрес профиля) — штатных
// тридцати секунд на это впритык.
test.describe.configure({ timeout: 60_000 });

test.beforeEach(({}, testInfo) => {
  test.skip(testInfo.project.name !== "internal-ui", "internal-ui only");
});

/** Разрешение браузера задаём сами: выдать его сайт не может, а тест обязан
 *  быть воспроизводимым. */
async function pretendPermission(page: Page, value: "default" | "granted" | "denied") {
  await page.addInitScript((permission) => {
    class FakeNotification {
      static permission = permission;
      static requestPermission = async () => permission;
      onclick: (() => void) | null = null;
      close() {}
    }
    Object.defineProperty(window, "Notification", { value: FakeNotification, configurable: true });
  }, value);
}

async function openProfile(
  page: Page,
  preference: { enabled: boolean; types: string[] },
  sessions: object = { items: [] },
) {
  // Порядок важен: в Playwright выигрывает маршрут, зарегистрированный
  // последним, поэтому общие заглушки идут первыми, частные — за ними.
  await page.route("**/api/v1/**", (route) => route.fulfill({ json: {} }));
  await page.route("**/api/v1/organizations/*/conversations/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/conversations/counters/")) {
      return route.fulfill({
        json: { all: 0, waiting: 0, mine: 0, ungrouped: 0, groups: [], agents: [], assignees: [] },
      });
    }
    if (path.endsWith("/conversations/directory/")) return route.fulfill({ json: { groups: [], employees: [] } });
    if (path.endsWith("/conversations/stats/")) return route.fulfill({ json: { waiting: 0 } });
    return route.fulfill({ json: { items: [] } });
  });
  await page.route("**/api/v1/organizations/*/company/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/company/onboarding/")) {
      return route.fulfill({
        json: { steps: {}, dismissedAt: "2026-01-01T00:00:00Z", completedAt: "2026-01-01T00:00:00Z" },
      });
    }
    return route.fulfill({ json: { items: [] } });
  });
  await page.route("**/api/v1/organizations/*/notifications/**", (route) =>
    route.fulfill({ json: { items: [], unreadCount: 0 } }),
  );
  await page.route("**/api/v1/organizations/*/notifications/messenger-bindings/", (route) =>
    route.fulfill({
      json: {
        items: [
          {
            integrationId: 1,
            provider: "TELEGRAM",
            name: "notify",
            botUsername: "chatballs_notify_bot",
            bound: true,
            pushTypes: ["DIALOG_WAITING"],
          },
        ],
        availableTypes: TYPES,
      },
    }),
  );
  await page.route("**/api/v1/organizations/*/notifications/preferences/BROWSER/", (route) =>
    route.fulfill({ json: { transport: "BROWSER", ...preference, availableTypes: TYPES } }),
  );
  // Соседние карточки профиля тоже ходят за данными: без их ответов страница
  // падает целиком и проверять было бы нечего.
  await page.route("**/api/v1/auth/profile/sessions/", (route) => route.fulfill({ json: sessions }));
  await page.route("**/api/v1/setup/", (route) => route.fulfill({ json: { needsSetup: false } }));

  // Вход формой: после него сессия обязана быть живой, иначе переход на адрес
  // профиля выкинет обратно на логин.
  let signedIn = false;
  await page.route("**/api/v1/auth/session/", (route) =>
    route.fulfill({
      json: signedIn ? { authenticated: true, user: OWNER } : { authenticated: false, language: "ru" },
    }),
  );
  await page.route("**/api/v1/auth/login/", (route) => {
    signedIn = true;
    return route.fulfill({ json: { authenticated: true, user: OWNER } });
  });

  await page.goto("/");
  await page.getByPlaceholder("you@domain.ru").fill("owner@example.com");
  await page.getByPlaceholder("Пароль").fill("Password-123");
  await page.getByRole("button", { name: "Войти" }).click();
  await page.goto(`/organizations/${ORGANIZATION_PUBLIC_ID}/profile`);

  const card = page.locator(".profile-card", { hasText: "Уведомления о рабочих событиях" });
  return { card, browserRow: card.locator(".profile-notifications-block").first() };
}

test("разрешение не запрошено — строку браузера можно включить", async ({ page }) => {
  await pretendPermission(page, "default");
  const { card, browserRow } = await openProfile(page, { enabled: false, types: [] });

  await expect(browserRow).toContainText("Этот браузер");
  await expect(browserRow).toContainText("Браузер спросит разрешение по нажатию");
  await expect(browserRow.getByRole("button", { name: "Включить" })).toBeVisible();
  // Галочки типов — только у включённого транспорта.
  await expect(browserRow.locator("input[type=checkbox]")).toHaveCount(0);
  // Строка бота осталась рядом и того же вида: шаблон у них один.
  await expect(card).toContainText("Telegram");
});

test("разрешение выдано и включено — видны те же галочки типов", async ({ page }) => {
  await pretendPermission(page, "granted");
  const { browserRow } = await openProfile(page, { enabled: true, types: ["DIALOG_WAITING"] });

  await expect(browserRow).toContainText("Включены");
  await expect(browserRow.getByRole("button", { name: "Отключить" })).toBeVisible();
  await expect(browserRow.locator("input[type=checkbox]")).toHaveCount(TYPES.length);
  // Под включённой строкой — примечание, что «Отключить» гасит показ, а не разрешение.
  await expect(browserRow).toContainText("Само разрешение остаётся выданным");
});

test("браузер отказал — вместо кнопки подсказка, как это снять", async ({ page }) => {
  await pretendPermission(page, "denied");
  const { browserRow } = await openProfile(page, { enabled: true, types: ["DIALOG_WAITING"] });

  await expect(browserRow).toContainText("Браузер запретил");
  // Кнопки «Включить» нет — она ничего не сделала бы; есть «Проверить снова».
  await expect(browserRow.getByRole("button", { name: "Включить" })).toHaveCount(0);
  await expect(browserRow).toContainText("Снять запрет можно только в браузере");
  await expect(browserRow.getByRole("button", { name: "Проверить снова" })).toBeVisible();
});

test("неполный ответ одной карточки не гасит всю страницу профиля", async ({ page }) => {
  // Регрессия: список сессий приходил без items, карточка падала на
  // items.length, и вместе с ней исчезала вся страница — пароль, двухфакторка
  // и уведомления в том числе.
  await pretendPermission(page, "default");
  const { card } = await openProfile(page, { enabled: false, types: [] }, {});

  await expect(card).toBeVisible();
  await expect(page.locator(".profile-card")).toHaveCount(7);
  await expect(page.locator(".sessions-card")).toContainText("Активные сессии");
});
