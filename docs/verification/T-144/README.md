# T-144 — проверка 14.10.2026

## Решения и окружение

Владелец разрешил: дополнение штатного API для ST13–ST14; обновление ветки
T-144 из main; временное назначение Светлане Петровой SUPERVISOR с одной
существующей группой в одноразовой БД задачи, отзыв группы и восстановление.
Ветка обновлена fast-forward до `e6620b2d`, включая опубликованную T-141.
Чужие рабочие копии и ветка main не изменялись.

Окружение `skaro-chatballs-t-144` запускалось и пересобиралось только через
Skaro. Frontend `http://localhost:20013`, backend-app `http://localhost:20011`.
Same-origin readiness `/api/v1/health/ready/` вернул
`database=true`, `redis=true`; PostgreSQL/Redis healthy. В запуск добавлен
документированный backend-admin без нового порта. Worker и worker-events работают.
DemoDataset организации 1 имел INSTALLED до проверки. Seed, mock API,
временные серверы, сброс паролей и искусственные оценки/анализы не использовались.

## Сборка и адресные проверки

Выполнены следующие команды в окружении задачи:

```powershell
docker compose exec -T frontend npm run build --workspace @chatballs/internal-ui
docker compose exec -T frontend npm run test --workspace @chatballs/internal-ui -- src/features/support-reports/access.test.ts src/features/support-reports/period.test.ts src/features/support-reports/presentation.test.ts src/features/support-reports/feedbackPresentation.test.tsx src/auth/access.test.ts src/router.test.ts
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/conversations/test_report_directory.py chatballs/conversations/test_team_result_scope.py
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/conversations/test_report_directory.py::ReportDirectoryTests::test_foreign_tenant_and_anonymous_directory_are_denied
docker compose exec -T backend-admin ruff check chatballs/conversations/report_directory.py chatballs/conversations/support_views.py chatballs/conversations/support_report.py chatballs/conversations/test_report_directory.py chatballs/identity/report_access.py chatballs/identity/policy.py
docker compose exec -T backend-admin python manage.py check
docker compose exec -T frontend npx tsc -p tsconfig.json
git diff --check
```

Сборка прошла (4262 модуля; штатное предупреждение о больших чанках Vite).
Первый запуск выявил TS-конфликт узкого типа Avatar с существующей строкой
приглашения; совместимость исправлена до успешной сборки. Фронтенд: 49 passed.
Сервер: 10 уникальных сценариев прошли. Первый запуск: 9 passed и один отказ
из-за ожидания 401/403 вместо штатного анонимного 404; после исправления ожидания
перезапущен только этот сценарий: 1 passed. Ruff и Django check прошли.
Полного набора не было; схема не менялась, использован --reuse-db.
Новые/изменённые файлы проверены на разделение ответственности и размеры.
После визуальной сверки навигация помещена в footer существующего дерева,
чтобы два flex-контейнера не создавали промежуток. Для этой небольшой правки
расположения полная сборка не повторялась по правилу владельца; выполнены
проверка типов и повторный браузерный сценарий на обновлённом окружении.
Ограниченный фильтр группы также сохраняет выделение из ST13, в том числе
при выборе всей текущей подконтрольной области.

## Браузер на реальном backend

Использован task-local Playwright MCP, существующие демо-учётные записи
Елены Кузнецовой и Светланы Петровой, отдельные браузерные контексты.
Начальная загрузка Vite дважды превысила timeout; повторная загрузка прошла.
Проверки выполнены на пересобранных текущих исходниках.

1. Администратор через штатный employees/update назначил Светлане SUPERVISOR
   с `supervisedGroupIds=[1]` («Операторы»), HTTP 200. Обычная группа 1 сохранена.
2. Навигация открыла `/organizations/9c14d363-8a6a-4933-816b-5f3cb5174f0e/statistics`.
   ST13: «Группы под вашим контролем: Операторы.», группа 1 в фильтре;
   группа 2 «Поддержка» отсутствует. В меню сотрудника и нагрузке ровно ID
   `[1,2,3,4,7]`, без Игоря Савельева (5) и Кирилла Волкова (6).
   Администраторский отчёт содержит `[1,2,3,4,5,6,7]`.
3. Разрешённые подключения: 2, 5, 22. Прямые фильтры `group=2`, `employee=5`,
   `connection=3` проверены для JSON/CSV/XLSX: все девять ответов 404.
   Административные настройки для супервизора: 403.
4. Реальные UI-скачивания CSV и XLSX выполнены через «Выгрузить».
   `team.csv` и `team.xlsx` проверены openpyxl/CSV-парсером: в обоих ровно
   ID `[1,2,3,4,7]`; формульных ячеек в XLSX нет. JSON отчёта показывает
   те же ID; ожидание ответа в каждой строке 0.
5. Вкладки оценок и качества показывают действующее пустое состояние
   «По выбранным фильтрам ничего нет». В API обе секции имеют count=0.
   Карточки диалога 1 в группе 1: оценки/анализ HTTP 200;
   диалога 30 в группе 2: оба HTTP 404.
6. При открытом отчёте начат XLSX и через штатный API отозвана группа
   (`supervisedGroupIds=[]`), HTTP 200. Скачивания не произошло.
   ST14 скрыл таблицы, вкладки и фильтры; «Выгрузить» disabled. Время
   `revokedAt=2026-10-14T17:05:47.185713+00:00` показано как 20:05 в Europe/Moscow.
   Доступ и справочники пустые; следующий отчёт содержит employees=[] и обе
   управленческие секции count=0. Повторные group=1 JSON/CSV/XLSX: 404.
7. После отзыва карточки оценки и анализа диалога 1 дают 404, обычная карточка
   этого же диалога — 200 благодаря независимому рабочему членству.
   «Статистика» сохранена на открытом ST14 (одна кнопка); после
   «Перейти к диалогам» кнопок «Статистика» нет.
8. Исходные права восстановлены через штатный API, HTTP 200: EMPLOYEE,
   supervisedGroups=[], обычная группа «Операторы» сохранена. Телефон и должность
   совпали с исходным снимком. Дополнительная READ ONLY SQL-сверка подтвердила
   роль EMPLOYEE и 0 связей контроля.

## Ограничения данных

В копии нет сохранённых клиентских оценок и успешных анализов качества.
Положительное наполнение таких карточек/распределений в браузере этой задачей
не заявляется. Значимые границы непустой команды, пустые состояния обеих
вкладок, запрет прямых чужих ID, реальные файлы, отзыв и сохранение обычных
рабочих прав проверены на настоящей БД. Сохранённые оценки и исходные/действующие
значения переиспользуют T-141/T-132/T-142; данные ради проверки не создавались.

## Артефакты

- `supervisor-report.png`, `supervisor-workload.png` — ST13 и текущая команда;
- `supervisor-ratings.png`, `supervisor-quality.png` — пустые состояния;
- `supervisor-revoked.png` — ST14 до перехода;
- `baseline-supervisor.png`, `baseline-revoked.png` — оригинальные ST13/ST14,
  открытые по file:// без изменения HTML и без временного HTTP-сервера;
- `team.csv`, `team.xlsx` — реальные скачивания;
- `verify-downloads.py` — читает JSON из stdin с base64 файлов и allowed IDs,
  проверяет одинаковую разрешённую команду и отсутствие формул.

Команда проверки скачанных файлов, выполненная в PowerShell:

```powershell
$downloadCheck = Get-Content docs/verification/T-144/verify-downloads.py -Raw
$downloadPayload = @{ csv=[Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $PWD 'docs/verification/T-144/team.csv'))); xlsx=[Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $PWD 'docs/verification/T-144/team.xlsx'))); allowed=@(1,2,3,4,7) } | ConvertTo-Json -Compress
$downloadPayload | docker compose exec -T backend-admin python -c $downloadCheck
```
