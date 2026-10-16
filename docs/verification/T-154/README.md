# Проверка T-154

14–15.10.2026. Оболочка проверена на исходниках задачи со штатным backend,
без mock API, временных HTTP-серверов, seed и сброса существующих доступов.

## Окружение и аккаунты

Skaro: `skaro-chatballs-t-154`. Frontend — `http://localhost:20004`,
backend-app — `http://localhost:20002`, platform — `http://localhost:20003`,
web-chat — `http://localhost:20005`. Браузер использовал IPv4-адреса этих же
портов. `docker compose ps` подтвердил PostgreSQL, Redis, оба backend,
frontend, web-chat и workers. `VITE_DEV_API_TARGET=http://backend-app:8000`.
Через frontend `/api/v1/health/ready/` вернул database=true и redis=true.
После изменений окружение повторно запускалось через `start_environment`.

В копии базы организации edevs установлен демо-набор: INSTALLED, 931 запись.
ADMIN: e.kuznetsova@atelie-nord.ru; EMPLOYEE: s.petrova@atelie-nord.ru.
В исходной копии базы SUPERVISOR отсутствовал. По прямому указанию владельца
«создай аккаунт, креды запиши в соответствующий файл» штатным API создан
`supervisor.t154@example.test`, id=11. Временный пароль заменён через штатную
форму первого входа; новому аккаунту назначена область контроля «Операторы».
Другие аккаунты, их пароли, роли и область контроля не изменялись.
Учётные данные сохранены локально в `test-results/T-154/accounts.json`
(каталог исключён из Git). Аккаунт принадлежит только окружению задачи.

## Навигация и логотип

ADMIN: все девять пунктов в порядке HTML. Геометрия измерена относительно
сайдбара и сравнена с G1: x=10px, ширина=199px, высота=36px;
y=60, 98, 136, 174, 212, 250, 303, 341, 379px. Шрифт совпал с HTML:
system stack, 13.5px; обычный вес 500, активный 600; gap=10px,
padding=0 10px. Разделитель имеет отступы 6px.
OWNER и ADMIN дополнительно проверены SSR-тестом одного компонента навигации.

EMPLOYEE: дерево, разделитель и Помощь, Статистика отсутствует.
SUPERVISOR: без области контроля Статистика отсутствует; с областью
«Операторы» сервер выдаёт reports.view и reports.export, Статистика видна
перед Помощью и открывает /statistics. Настройки отсутствуют.
Отдельная роль и ограничения SUPERVISOR сохранены.

Помощь — нативный a, target=_blank, rel="noopener noreferrer".
Проверены focus-visible и Enter: новая вкладка открыла
`https://chatballs.com.edevs.tech/`, заголовок Chatballs.
Hover: фон rgb(240,240,240), текст rgb(31,31,31) в светлой теме;
circle-help 17px / stroke 1.9, внешняя стрелка 13px / stroke 2.

SVG логотипа побайтно совпадает с assets/logo-sunset.svg. Меню, рейка и
мобильное раскрытие: 28 × 14.921875px. AuthFrame: 52 × 27.71875px;
онбординг: 28 × 14.921875px и 22 × 11.71875px; HelpLayout:
28 × 14.921875px в шапке и 22 × 11.71875px в подвале.
Favicon в dev и сборке ссылается на тот же SVG-ресурс.
Пользовательский логотип проверен SSR в рейке и полном меню: оба img
сохраняют адрес организации, стандартный знак не выводится. Для них
сохранены размеры контейнера и object-fit:contain.

Браузер: ADMIN, EMPLOYEE и SUPERVISOR; desktop 1440×900, рейка
1024×768, мобильное раскрытие 390×844. Светлая и тёмная темы применялись
штатной applyAppearance без сохранения предпочтений аккаунтов.
Снимки каждой роли и мобильного меню сохранены рядом. Исходные HTML
просмотрены через file://; для темы/кадра использован __dcSetProps рантайма.
Сравнительные снимки: baseline-admin-*, baseline-employee-light,
baseline-supervisor-light, baseline-rail и соответствующие снимки реализации.
Вложенные редактор/передача не использовались для проверки оболочки.

## Агент и клиентский виджет

Единственный продуктовый источник контура — packages/ui/src/AgentIcon.tsx.
Тест сверяет полный d с I.robot исходного chat-model.js. Поиск старого
M6 6a2 и chatballs-logo-mask в продуктовых TSX не дал совпадений.
Перечень всех прямых и условных обращений к robot — agent-usage.txt.
Он покрывает меню/дерево, агентов, фильтры и ленту диалогов, карточку и
диалоги контакта, подключения, знания, привязки материалов и статьи портала.
Все эти места проходят через общий Icon; размеры и цвета вызывающих
компонентов сохранены. В браузере дополнительно проверены список/карточка
агента (20px / 1.9 и 28px / 1.8), дерево (11px / 2.2), диалог и контакты.

BotIcon клиента сохранён по baseline «Веб-чат · поля и оформление»:
viewBox 48×48, заливка и wcBotBlink. В реальном web-chat измерено моргание;
в штатном предпросмотре — animation:none. Режим «Без иконки» убрал знак
только из шапки, сохранив кнопку; изменение осталось несохранённым.
Загруженный адрес и null дополнительно проверены SSR-тестом WidgetIcon.
На текущем origin web-chat показывает штатное «Чат временно недоступен»:
в существующей конфигурации разрешён другой origin. Разрешённые домены
не менялись; работа переписки клиента в этой проверке не утверждается.

## Выполненные команды

В frontend-контейнере отсутствует mount design; для адресного сравнения
векторов копировались оригинальные файлы, без изменения макетов:

```powershell
docker compose cp ./design/. frontend:/app/design/
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run build
docker compose exec -T frontend npm --workspace @chatballs/ui run typecheck
docker compose exec -T web-chat npm --workspace @chatballs/web-chat run build
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run typecheck
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run test -- src/auth/access.test.ts src/i18n/catalog.test.ts src/features/integrations/appearance/IconSettings.test.tsx
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run test -- src/layout/SidebarNavigation.test.tsx
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run test -- src/shared/branding.test.tsx
git diff --check
```

Обе сборки и typecheck успешны, адресные тесты: 11 + 6 + 5 = 22 прошли.
Полный набор не запускался. Локальные npm-команды до установки зависимостей
не смогли стартовать; итоговая проверка выполнена в штатных контейнерах.
Промежуточные ошибки теста/типизации исправлены и повторно проверены.

NO GOD FILES: Sidebar уменьшен до 94 строк; SidebarNavigation — 92,
ChatScopeTree — 94; новые модули — не более 92 строк. icons.tsx уменьшен
до 175 строк, layout/styles.css уменьшен на 46 строк; новые стили и
переводы вынесены отдельно. Loader, backend и дизайн-файлы не изменялись.
Новых продуктовых экранов и согласований отклонений от дизайна нет.
