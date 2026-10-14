# Проверка T-156 — 15.10.2026

## Результат

Сборка TypeScript/Vite и 26 адресных frontend-тестов прошли. Серверный набор:
49 passed; после последней правки расчёта повторены только затронутые файлы:
21 passed. Линтер изменённых Python-файлов и `git diff --check` прошли.
Полный набор тестов не запускался.

## Штатный контур

Skaro создал копию существующей базы и запустил среду `skaro-chatballs-t-156`.
Адреса проверки: frontend `http://localhost:20010`, backend-app
`http://localhost:20008`, platform `http://localhost:20009`, web-chat
`http://localhost:20011`. PostgreSQL/Redis/backend имеют healthy; init завершён
с кодом 0. Readiness через frontend: `status=ok`, `database=true`, `redis=true`.
В frontend подтверждён `VITE_DEV_API_TARGET=http://backend-app:8000`.
Демо-набор уже установлен: organization=1, INSTALLED, 931 записей.
Использован существующий ADMIN Елена Кузнецова. Seed, смена паролей, ролей
или учётных данных не выполнялись. Правки данных проверки относятся только
к копии T-156; API и backend не подменялись.

Первоначально копирование было заблокировано остановленной основной БД
`chatballs-postgres-1: Exited (255)`. По прямому указанию владельца «запускай»
выполнен `docker start chatballs-postgres-1` без пересоздания. PostgreSQL
завершил восстановление, стал healthy, после чего повторный запуск Skaro
создал среду задачи. В команду среды через configure_environment включён
документированный backend-admin для серверных тестов.

Первая загрузка исходного модуля Vite долго не завершалась. Браузерная
проверка выполнена на штатной production-сборке `/dist/index.html`, которую
обслуживает тот же frontend с тем же API-прокси. Этот способ описан в
`docs/transfer-frontend.md`; отдельный сервер не создавался. Использован
task-local Playwright. На старте были таймауты загрузки/ожидания данных;
сценарии ниже проверены после получения настоящих ответов. Во время закрытия
обращения соседний запрос email/options вернул 409; формы и отчёты успешно
работали, тестовые запросы к отсутствующим API не подставлялись.

## Исполняемые проверки

```powershell
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run build
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run build -- --base=/dist/
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run test -- src/features/support-reports/partialPresentation.test.tsx src/features/support-reports/presentation.test.ts src/features/quality/settingsModel.test.ts src/features/quality/serialization.test.ts src/features/ratings/settingsModel.test.ts src/features/handling-rules/model.test.ts src/i18n/catalog.test.ts
docker compose exec -T backend-admin pytest chatballs/conversations/test_support_partial_report.py chatballs/conversations/test_support_report.py chatballs/conversations/test_support_timeline.py chatballs/conversations/quality/test_settings_suggestions.py chatballs/conversations/quality/test_criteria.py chatballs/conversations/quality/test_ui_contract.py chatballs/conversations/quality/test_timing_purge.py chatballs/ratings/test_settings_defaults.py chatballs/conversations/rules/test_rule_api.py chatballs/i18n/tests.py::CatalogTests --reuse-db -q
docker compose exec -T backend-admin pytest chatballs/conversations/test_support_partial_report.py chatballs/conversations/test_support_report.py chatballs/conversations/test_support_timeline.py chatballs/conversations/quality/test_timing_purge.py --reuse-db -q
docker compose exec -T backend-admin python manage.py verify_support_exports
```

Обе сборки успешны. Vite предупреждает о существующих больших chunk;
backend — о deprecated CheckConstraint и отсутствующем staticfiles.
verify_support_exports повторён после последней правки и реального принятия/
закрытия: READ ONLY, organization=1, conversations=20, parameter_sets=5;
API/CSV/XLSX совпадают по значениям, единицам, полноте и деталям.

Ruff выполнен для support_metrics.py, support_report.py, support_export_rows.py,
test_support_partial_report.py, test_support_report.py, quality/criteria.py,
quality/settings_presentation.py, quality/views.py, quality/test_settings_suggestions.py,
i18n/messages/quality_ru.py и quality_en.py; все проверки успешны. После
последней правки отдельно повторены support_metrics.py и support_report.py.

## Статистика: критерии 1–2

Выбран штатный период 9–15 октября, Europe/Moscow; сбор доступен с
14 октября 20:36:03. Обычными кнопками «Взять диалог» и «Закрыть диалог»
обработано существующее обращение 31 в копии задачи; сообщения клиентам
для проверки не отправлялись. Анализ качества и клиентские оценки выключены.

В API и интерфейсе: принято=1, завершено=1, обработка=38,131181 с
(интерфейс 38,13 с). Неполнота периода и доступная дата показаны. Строка
Елены содержит те же 1/1 и обработку; tooltip ячейки сообщает неполноту.
График: за 15 октября столбцы 1/1, 9–14 октября значения неизвестны, до
проверочного события доступный день показывал настоящий 0. Неизвестные
последующие ответы и ненаблюдаемые передачи остаются «—».

[Карточки и график](statistics-partial.png), [сотрудники](statistics-employees.png).
Штатными кнопками скачаны support-report-2026-10-09-2026-10-15.csv и .xlsx;
XLSX download.failure=null, CSV также успешно скачан. Адресные серверные
тесты проверяют неполный период, границы выборок, фильтры, исторические
измерения, текущие интервалы, организацию и права супервизора, немедленный
отзыв доступа, физическое удаление и согласованность обоих экспортов.
Карточка анализа качества сохраняет прежнее поведение неполных времён;
наблюдаемые значения включены только для отчётов.

## Правила и оценки: критерии 3–4

У подтверждения отсутствует readonly-ввод получателя (0 таких полей), клиент
назван в существующем описании правила. Через UI изменены и сохранены срок
15 минут и текст с {срок}; у уведомления — 20 минут, условие готовности и
получатель «Руководство». Получены два отдельных PATCH только с изменёнными
полями. Повторное открытие сохранило все значения. Исходные значения обоих
правил восстановлены штатным PATCH, версии 3; остальные правила не менялись.
[Подтверждение](rules-receipt.png), [условия и получатели](rules-saved.png).

В оценках отсутствует readonly-поле шкалы и служебное пояснение; виден ряд
1–5. Через UI сохранены подпись пятёрки, текст запроса и задержка 12 минут
(720 секунд), затем подтверждены повторным открытием. После проверки
восстановлены исходные выключенные настройки штатным API.
[Сохранённая форма](ratings-saved.png).

## Анализ качества: критерии 5–6

До первого сохранения API вернул enabled=false, criteriaVersion=null,
criteria=[] и три предложения baseline. При открытии и отмене правки версия
не появилась. В UI видны названия, полные описания и шкалы «Да / Нет», 1–5,
1–5. Предложения формируются на языке организации через backend i18n.
[Начальный экран](quality-initial.png).

Проверено последовательно: отмена изменения описания; явное сохранение
предложений как версии 1 без включения; изменение описания и сохранение
версии 2; создание четвёртого критерия с описанием/шкалой и отмена всех правок
(снова три строки); удаление трёх критериев и сохранение пустой версии 3.
После перехода в другой раздел и обратно версия 3 сохранила пустую таблицу,
предложения не вернулись: [пустой сохранённый набор](quality-cleared.png).
Для дальнейшего просмотра исходные три критерия восстановлены штатным PUT
как версия 4, анализ выключен. Прошлые версии не удалялись и не переписывались.
Сохранность снимка критериев прошлого анализа проверена серверным
QualityUIContractTests.test_named_versions_preserve_historical_job_and_required_fields.

## Дизайн, i18n и размер: критерий 7

Источники — design/baseline/platform-expansion/Настройки · новые разделы.dc.html
и Статистика и качество.dc.html. Исключения ограничены согласованными в задаче
удалениями псевдополей и служебного текста. Новых экранов и стилей нет;
использованы существующие строки, компоненты и состояния черновика/версии.
Пользовательские строки предложений находятся в backend-каталогах ru/en;
frontend и backend каталог проверены адресными тестами и TypeScript.

Изменённые файлы измерены: наибольший файл кода — test_support_report.py,
192 строки; QualitySettings.tsx — 46 строк, support_report.py — 106 строк.
Расчёт, экспорт, представление, локальный редактор и подготовка предложений
разделены; файлов кода свыше 300 строк и компонентов свыше 180 строк нет.
