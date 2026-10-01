# Разработка визуальной темы портала

Для разработчика, который добавляет новое оформление публичных страниц Help Center. Основание — ADR-0022, SPEC-0014.

Не входит: оформление интерфейса организации (персональная тема и акцент, `shared/appearance.ts`), вёрстка новых блоков портала, изменение состава страниц.

## 0. Что такое тема

Папка в репозитории, переопределяющая CSS-переменные публичной части портала. Без JS, без подмены компонентов; разметка и правила Help Center общие, тема меняет значения токенов и при необходимости добавляет правила в своём скоупе. Владелец выбирает тему: `Порталы → <портал> → Настройки → Оформление`. Портал хранит только id темы — изменений в БД, API и миграциях не нужно.

## 1. Где что лежит

```text
apps/internal-ui/src/features/help-center/
├── themes/
│   ├── README.md          краткая памятка
│   ├── contract.css       все токены --help-* и значения по умолчанию
│   ├── types.ts           тип манифеста
│   ├── registry.ts        автообнаружение тем, выбор темы и схемы
│   ├── usePortalTheme.ts  применение темы к документу
│   ├── registry.test.ts   тесты каталога = линтер правил тем
│   └── classic/           тема по умолчанию (шаблон)
│       ├── manifest.ts
│       └── theme.css
├── styles-layout.css      вёрстка Help Center: только --help-*
├── styles-home.css
├── styles-article.css
└── styles-responsive.css
```

Регистрировать тему где-либо ещё не нужно — достаточно папки.

## 2. Быстрый старт

1. `cp -r apps/internal-ui/src/features/help-center/themes/classic apps/internal-ui/src/features/help-center/themes/aurora`
2. Заполнить `aurora/manifest.ts`; `id` равен имени папки.
3. Переопределить токены в `aurora/theme.css` под `html[data-portal-theme="aurora"]`.
4. `npm --workspace @chatballs/internal-ui run test`
5. Выбрать тему в настройках портала и посмотреть публичную страницу.

## 3. Манифест

```ts
import type { PortalThemeManifest } from "../types";

export const manifest: PortalThemeManifest = {
  id: "aurora",                     // == имя папки, [a-z0-9-]
  name: "Аврора",                   // видит владелец портала
  description: "Светлое оформление с синим акцентом и крупными скруглениями.",
  schemes: ["light", "dark"],       // только реально проверенные схемы
  preview: { bg: "#f7f8fc", ink: "#1a1c25", accent: "#4c5fd7" },
  author: "Имя или команда",        // необязательно
};
```

- `name` и `description` — пользовательский текст без служебной лексики; `description` показывается под заголовком «Оформление».
- Нет тёмных значений — оставить `["light"]`: тёмная схема не предлагается, сохранённая деградирует до светлой.
- `preview` — подложка, текст, акцент.

## 4. Файл стилей

```css
html[data-portal-theme="aurora"] {
  --help-bg: #f7f8fc;
  --help-surface: #ffffff;
  --help-accent: #4c5fd7;
  --help-accent-ink: #ffffff;
  --help-radius-lg: 18px;
}
html[data-portal-theme="aurora"][data-theme="dark"] {
  --help-bg: #12131a;
  --help-surface: #191b23;
  --help-accent: #7d8cf0;
}
html[data-portal-theme="aurora"] .help-category-icon {
  box-shadow: 0 6px 18px rgba(76, 95, 215, 0.28);
}
@media (max-width: 560px) {
  html[data-portal-theme="aurora"] .help-hero { margin-top: 24px; }
}
```

Правила скоупа: каждое правило начинается с `html[data-portal-theme="<id>"]`, включая внутри `@media` и `@supports`; `@keyframes` с префиксом id темы; `@font-face` допустим, файл шрифта в репозитории.

## 5. Справочник токенов

**Типографика:** `--help-font-body` (`Inter, "Segoe UI", Helvetica, Arial, sans-serif`; основной шрифт), `--help-font-heading` (`var(--help-font-body)`; логотип-название и заголовки), `--help-font-mono` (`var(--font-mono)`; код), `--help-heading-weight` (`650`).

**Поверхности:** `--help-bg` (`var(--surface-card)`; подложка, boot-загрузчик, «портал не найден»), `--help-surface` (`var(--surface-card)`; карточки разделов, панель поддержки, кнопки), `--help-surface-soft` (`var(--n-9)`; ховеры, шапки таблиц), `--help-surface-raised` (`var(--n-10)`; компактный поиск, шиммер), `--help-surface-strong` (`var(--n-7)`; ховер строк поддержки), `--help-skeleton` (`var(--n-8)`; плейсхолдеры статьи).

**Текст:** `--help-ink` (`var(--n-1)`; заголовки, названия, точки загрузчика), `--help-text` (`var(--n-2)`; иконка поиска, кнопки оценки), `--help-text-muted` (`var(--n-3)`; описания, breadcrumbs, содержание, подвал), `--help-text-subtle` (`var(--n-4)`; счётчики, дата, фокус поиска).

**Линии:** `--help-line` (`var(--n-6)`; разделители, рамки таблиц и кнопок), `--help-line-soft` (`var(--n-7)`; шапка, подвал, панель поддержки).

**Акцент:** `--help-accent` (`var(--n-1)`; плитка иконки раздела, плавающая кнопка поддержки), `--help-accent-hover` (`color-mix(in srgb, var(--help-accent) 85%, black)`), `--help-accent-ink` (`var(--surface-card)`; содержимое на акценте).

**Код:** `--help-code-bg` (`var(--n-1)`, в тёмной `var(--n-10)`), `--help-code-ink` (`var(--n-9)`, в тёмной `var(--n-1)`), `--help-code-inline-bg` (`var(--n-9)`).

**Форма и тень:** `--help-radius-xs` 5px, `-sm` 7px, `-md` 10px, `-lg` 12px, `-xl` 16px, `-2xl` 18px, `-pill` 999px; `--help-shadow-panel` (`var(--shadow-lg)`).

## 6. Тёмная схема

Схема выбирается владельцем портала (Светлая / Тёмная / Как в системе) и применяется `data-theme` на `<html>` — тем же механизмом, что у интерфейса; второй механизм вводить нельзя. Тёмные значения — под `html[data-portal-theme="<id>"][data-theme="dark"]`. Тема на значениях по умолчанию получает тёмную схему бесплатно; тема с фиксированными цветами обязана прописать тёмные значения полностью.

## 7. Проверка

```bash
npm --workspace @chatballs/internal-ui run test
npm --workspace @chatballs/internal-ui run typecheck
npm --workspace @chatballs/internal-ui run build
```

Сборка кладёт CSS темы в отдельный ленивый чанк `assets/theme-*.css`. `registry.test.ts` не пропустит: несовпадение id и папки, дубликаты; пустые `name`/`description`, пустой или неизвестный `schemes`; отсутствие `theme.css`; правило вне скоупа (в том числе в `@media`); `@keyframes` без префикса; токен вне контракта.

Ручная проверка: обе схемы, главная, статья, поиск, пустой результат, загрузка, мобильная ширина; консоль без ошибок и предупреждений.

## 8. Что теме нельзя

JS и подмена компонентов; глобальные правила; правка чужих файлов (`contract.css`, `styles-*.css`, другие темы — кроме §9); свои переменные вне контракта; внешние ресурсы (CDN); собственная тёмная тема через `@media (prefers-color-scheme)`.

## 9. Если рычага не хватает

Нет нужного токена — дефект контракта: добавить токен в `contract.css` со значением, равным текущему поведению; заменить литерал в `styles-*.css` на токен; проверить, что вёрстка не содержит `--n-*`, `--surface-*` и литеральных цветов; дополнить справочник и `themes/README.md`.

## 10. Жизненный цикл темы

Удалённая из сборки тема деградирует до `classic`, в настройках показывается недоступной. Переименование папки — новая тема; при необходимости — миграция данных по согласованию с владельцем. `classic` ничего не переопределяет; менять её вид — отдельное решение владельца.

## 11. Чек-лист перед коммитом

- id совпадает с папкой; `name` и `description` без служебной лексики.
- `schemes` проверены в браузере.
- Все правила скоупнуты, `@keyframes` с префиксом, только токены контракта.
- `test`, `typecheck`, `build` проходят.
- Публичная страница проверена в схемах, на десктопе и мобильной ширине; консоль чистая.
- Другие темы, контракт и вёрстка не тронуты (или §9 выполнен целиком).