# Проверка T-141

14.10.2026. Проверки реализации завершены с согласованным исключением приёмки:
заполненные отчёты проверены на явно обозначенных тестовых записях штатного backend.
Это не результаты реального вызова AI и не реальные оценки клиентов.

## Окружение

Штатное окружение Skaro `skaro-chatballs-t-141` на исходниках задачи:
frontend `http://localhost:20004`, backend-app `http://localhost:20002`,
platform `http://localhost:20003`, web-chat `http://localhost:20005`.
`docker compose ps` подтвердил backend-app, backend-admin, frontend,
postgres, redis и штатные workers. Frontend использует
`VITE_DEV_API_TARGET=http://backend-app:8000`.
Readiness через frontend: database=true, redis=true.

Для адресных тестов документированный backend-admin включён в команду запуска
через configure_environment. Сервисы запускались только инструментом Skaro.
Схема не менялась, тесты используют --reuse-db. Полный набор не запускался.

## Исполненные команды

Сборка прошла; Vite сообщил штатное предупреждение о крупных chunks:

```powershell
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run build
```

Выбранные серверные сценарии — расчёты, новые формулы, доступ, экспорт,
метаданные критериев, явное отсутствие оценки, AI-валидация и i18n:

```powershell
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/conversations/test_support_feedback.py chatballs/conversations/test_support_feedback_summaries.py chatballs/conversations/test_support_feedback_access.py chatballs/conversations/quality/test_criteria.py chatballs/conversations/quality/test_execution.py chatballs/conversations/quality/test_api.py chatballs/i18n/tests.py::CatalogTests
```

Из 40 сценариев 38 прошли в первом прогоне. Две ошибки новых проверок исправлены:
обновление снимка sent_at в тесте границ и фиксированная историческая верхняя
граница для сравнения трёх отдельных запросов экспорта. Повтор ниже: 2 passed.

```powershell
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/conversations/test_support_feedback_summaries.py::FeedbackSummaryTests::test_sent_cohort_and_received_scores_have_separate_half_open_boundaries chatballs/conversations/test_support_feedback_access.py::FeedbackAccessTests::test_http_json_csv_xlsx_feedback_values_match_and_strings_cannot_be_formulas
```

После добавления в экспорт долей распределения повторены только затронутые
экспорт и каталог: 6 passed.

```powershell
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/conversations/test_support_feedback_access.py::FeedbackAccessTests::test_http_json_csv_xlsx_feedback_values_match_and_strings_cannot_be_formulas chatballs/i18n/tests.py::CatalogTests
```

Фронтенд: заключительный общий адресный прогон дал 11 passed:
8 существующих проверок периода и представления и 3 новые проверки.
Язык проверок явно выбран; влияние изменения на соседние проверки исключено.

```powershell
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run test -- src/features/support-reports/feedbackPresentation.test.tsx src/features/support-reports/presentation.test.ts src/features/support-reports/period.test.ts
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run test -- src/features/support-reports/feedbackPresentation.test.tsx
```

Ruff по изменённым серверным модулям и `git diff --check` прошли.
Новые компоненты, модули и изменённая страница меньше 180 строк.
Имеющиеся большие ru/en каталоги менялись только для импорта/spread отдельного
словаря support-feedback; новые строки не добавлены в их основной массив.

READ ONLY проверка существующих данных под runtime-ролью chatballs_app:

```powershell
Get-Content docs/verification/T-141/inspect-runtime.py -Raw | docker compose exec -T backend-app python manage.py shell
```

Первоначальный результат: HTTP 200, 20 существующих обращений, ratingCount=0,
scaleSummaryCount=0, qualityCount=0, versionCount=0, все состояния качества — 0.
Тестовые данные адресных pytest-проверок находятся в отдельной тестовой БД;
они не использовались как данные приложения для браузерной проверки.

## Первичная браузерная проверка штатного приложения

Playwright MCP задачи. Наличие документированных ADMIN Анны Ким и EMPLOYEE
Светланы Петровой проверено чтением существующей базы до входа.
Учетные данные, TOTP, роли и права не изменялись. Ознакомительное окно закрыто
обычной кнопкой, настройка установки не запускалась.

- ADMIN открывает `/organizations/9c14d363-8a6a-4933-816b-5f3cb5174f0e/statistics`.
  Обе новые вкладки есть. Пустые реальные секции API отображаются утверждённым
  состоянием ST10; выгрузка отключена. Историческая неполнота событийных
  длительностей не переносится на оценки и качество.
- employee=3 оставляет ровно строку сотрудника 3; transport=WEB, group=2,
  connection=5 последовательно добавляются в общий запрос с тем же периодом
  и Europe/Moscow. Реальный backend вернул HTTP 200 для всех этих наборов.
  Значения полученных оценок и анализов во всех случаях отсутствуют.
- Отключение сети browser context (без перехвата/замены API) при сбросе фильтров
  показало ST12. После восстановления сети «Повторить» вернуло пустой результат.
- EMPLOYEE открывает прямой маршрут статистики: экран «403 · Доступ запрещён».
  Командный API возвращает HTTP 403. Собственный базовый API с employee=4
  возвращает 200, но customerRatings и qualityAnalysis имеют state=forbidden,
  count=null, пустые scaleSummaries/versions и details.
- Ошибки сети при перезапуске Skaro и искусственном отключении сети были
  ожидаемыми диагностическими событиями; после штатной готовности приложение
  загрузилось. Таймаут ожидания перенаправления EMPLOYEE не был отказом
  приложения: маршрут сохраняется и показывает экран запрета, что проверено.

Снимки `ratings-empty.png` и `quality-empty.png` показывают только реальный
пустой результат. Они не доказывают внешний вид заполненных ST4–ST5.

## Согласованное исключение и заполненная проверка

После повторной READ ONLY проверки владелец выбрал в карточке:
«Разрешить тестовые записи и это исключение приёмки».
Карточка явно согласовывала тестовые оценки и анализы в копии данных T-141,
через проектные сервисы, и исключение из требования «с реальными результатами».
Новые провайдеры, mock API и изменения аккаунтов не разрешались и не выполнялись.

В одной транзакции create-review-records.py создал четыре помеченных тестовых
обращения с принятием, публичными ответами, завершением, запросами оценок,
валидированными тестовыми заключениями и корректировками через штатные сервисы.
Использованы существующие ADMIN user_id=3 и 2, WEB-подключения 5 и 6, группы 1 и 2.
После создания обе функции выключены; аккаунты, права и настройки провайдеров
не изменялись. Реальных AI-вызовов при подготовке не было.

| Обращение | Группа / подключение | Ответили | Оценка | Качество |
|---|---|---|---|---|
| 32 | 1 / 5 | 3, 2 | 5, первая шкала | версия 2; решение исправлено |
| 33 | 2 / 6 | 2 | 4, первая шкала | версия 2 |
| 34 | 1 / 5 | 3 | 2, новая шкала | версия 3; решение без оценки; исходный тон 0, действующий 6 |
| 35 | 2 / 6 | 3 | запрос отправлен, ответа нет | версия 3; приветствие без оценки |

Версия 1 без анализов проверяет отсутствующие значения. READ ONLY сверка
под chatballs_app после создания: HTTP 200, 24 обращения, ratingCount=3,
scaleSummaryCount=2, qualityCount=4, versionCount=3; SUCCEEDED=4, остальные — 0.

Команда ниже — аудит выполненного действия, не автоматическое наполнение
при интеграции. Скрипт останавливается при другом имени окружения,
существующих записях или изменённых настройках:

```powershell
if ($env:COMPOSE_PROJECT_NAME -ne 'skaro-chatballs-t-141') { throw 'Wrong task environment' }
Get-Content docs/verification/T-141/create-review-records.py -Raw | docker compose exec -T -e T141_REVIEW_PROJECT=$env:COMPOSE_PROJECT_NAME backend-app python manage.py shell
```

Исходные ST4–ST5 открыты по file://, снимки baseline-ratings.png и
baseline-quality.png — отдельные дизайн-референсы. Временных серверов нет.
Заполненное приложение повторно проверено через Playwright MCP:

- ST4: две отдельные пары таблиц; средние 4,5 и 2, количества 2 и 1,
  доли ответивших 100% и 50%. Общего среднего нет. Подписи из снимков API.
  Строки сотрудников пересекаются; отсутствующие оценки отображаются «—».
- ST5: три версии, семь критериев. Каждое среднее, количество исправлений
  и отсутствующих оценок сопоставлено с JSON API без расхождений.
  Версия 3: приветствие 100% и без оценки 1; решение 5 и без оценки 1;
  тон 8 и исправлено 1. Версия 2: 50%, 3,5 и 4,5. Исправлено 50% анализов
  каждой заполненной версии. Версия 1: ноль анализов, показатели строк «—».
- Визуальная сверка выявила тесный первый заголовок ST4. Учтены ширина
  колонки 40px, промежутки и общие отступы: первая ячейка 66px,
  overflow=hidden. Фон, размер 12px и отступы примечаний приведены к HTML.
  Макет не менялся. Общие компоненты и оболочка приложения сохранены.
- employee=3 даёт 2 оценки / 3 анализа и одну строку сотрудника;
  дополнительный group=1 — 2/2. transport=WEB и connection=5 сохраняют 2/2.
  Исходный тон 0 остаётся 0 в API, действующий — 6; неоценённое решение — «—».
  transport=EMAIL сбрасывает подключение и даёт 0/0: все семь средних — «—».
  «Сбросить» возвращает полный набор 3/4. Все ответы — HTTP 200.
- Период 1–7 октября даёт 0/0. UTC меняет границы на
  2026-10-08T00:00:00Z — 2026-10-15T00:00:00Z и сохраняет 3/4.
- EMPLOYEE Светлана Петрова проверена на заполненной базе отдельным browser
  context: экран 403, командный JSON и оба экспорта — HTTP 403. Собственный
  employee=4 — 200; управленческие секции forbidden/count=null, пустые
  scaleSummaries/versions/details. Роли и учётные данные не менялись.

Снимки: ratings-filled.png, ratings-second-scale.png, quality-filled.png, quality-filtered.png,
employee-denied.png. При возобновлениях Skaro были холодные загрузки Vite
с таймаутами навигации; после готовности проверена текущая страница.
Первый CSV-клик не породил запроса; повторное штатное скачивание прошло с 200.

CSV скачан из оценок, XLSX — из качества; review.csv и review.xlsx являются
фактическими browser downloads. Две шкалы, семь критериев, исходные и действующие
значения и доли совпали. Формульных ячеек нет. Проверка чисел учитывает
эквивалентность 5.0 в CSV и 5 в XLSX:

```powershell
$t141Downloads = @{ csv = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path (Get-Location) 'docs/verification/T-141/review.csv'))); xlsx = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path (Get-Location) 'docs/verification/T-141/review.xlsx'))) } | ConvertTo-Json -Compress
$t141Verifier = Get-Content docs/verification/T-141/verify-downloads.py -Raw
$t141Downloads | docker compose exec -T backend-admin python -c $t141Verifier
```

Последующий шаг менял только CSS и доказательства: повторная сборка для
локальных CSS-правок не запускалась по правилу владельца. Browser-проверка
текущего CSS выполнена после start_environment. Ruff и git diff --check прошли.
Новые проверочные скрипты меньше 180 строк. Супервизорская и tenant-изоляция
проверены серверными тестами; новых ролей для браузера не назначали.
Все критерии проверены с учётом указанного исключения; статус задачи
зависит от принятия и публикации результата Skaro.

## Совместимость с контрактом качества из свежей main

После принятия трёх критериев Skaro сообщил о конфликтах с T-142 в criteria.py
и presentation.py. Подготовлены совместимые изменения без слияния веток:
ограничение имени критерия 200 символами, сохранение reporting.positiveValue,
effectiveScaleIndex с точным типом значения и null для отсутствующей оценки,
сохранение исходного missingReason после корректировки.

Адресные проверки: 12 passed; Ruff и git diff --check прошли.
Новые/изменённые серверные файлы этого шага меньше 100 строк.
Сборка frontend повторена и прошла, только прежнее предупреждение о chunks.

```powershell
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/conversations/quality/test_criteria.py chatballs/conversations/quality/test_api.py chatballs/conversations/quality/test_missing_presentation.py
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run build
```

После start_environment READ ONLY сверка сохранила 24 обращения, 3 оценки,
2 шкалы, 4 анализа и 3 версии. Playwright повторно открыл заполненное качество:
все три версии и прежние средние отображаются. Штатный GET quality/jobs/3/
в авторизованном browser context вернул HTTP 200: resolution — originalValue=null,
effectiveValue=null, effectiveScaleIndex=null, missingReason=insufficient_messages;
tone — originalValue=0, effectiveValue=6, effectiveScaleIndex=6.
Холодная загрузка Vite и ожидание неверной подписи заголовка дали таймауты;
после загрузки проверен фактический заголовок «Набор критериев · версия 3».
Merge main не выполнялся: ожидается ответ на карточку разрешения согласно
прямому ограничению окружения на слияние без просьбы владельца.

## Разрешённое слияние main и заключительная проверка

Владелец явно разрешил merge main в T-141. В ветку задачи влита main 0aba0940;
конфликты criteria.py/presentation.py разрешены с сохранением обоих контрактов.
Новый редактор критериев сохраняет reporting.positiveValue при сериализации.
Типы заключений и редактора допускают null: отсутствующая оценка показывается
существующим обозначением «—», корректировка требует явного выбора шкалы.
Новых блоков, текстов, иконок или layout нет.

После start_environment на объединённых исходниках: 15 серверных и 16 frontend
проверок прошли. Сборка frontend, Ruff и diff --check прошли; изменённые модули
этого шага — 13–123 строки. Полный набор не запускался.

```powershell
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/conversations/quality/test_criteria.py chatballs/conversations/quality/test_api.py chatballs/conversations/quality/test_missing_presentation.py chatballs/conversations/quality/test_ui_contract.py
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run test -- src/features/quality/serialization.test.ts src/features/quality/review.test.tsx src/features/quality/presentation.test.ts src/features/support-reports/feedbackPresentation.test.tsx
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run build
```

Playwright: /conversations/34/quality показывает исходный 0 и действующий 6,
неоценённое решение — «—». API job3 HTTP 200: индекс отсутствующей оценки null,
индекс исправленного тона 6. «Исправить» у неоценённого критерия открывает пустой
Select без выбранного балла; «Отмена» закрывает редактор. Данные не менялись.
Отчёт после ожидания штатной загрузки дневных запросов показывает три версии
и прежние средние/пропуски. Readiness через frontend HTTP 200:
database=true, redis=true. READ ONLY: 24 обращения, 3 оценки, 2 шкалы, 4 анализа,
3 версии. Таймауты холодной загрузки и ожидания дневных данных не скрывались;
после завершения загрузки проверены заполненные таблицы.
