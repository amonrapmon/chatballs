# Серверные границы командных результатов

Реализация SPEC-0029 R-5/R-7 (T-139), без изменений интерфейса и схемы БД.

`conversations.management_scope` перечитывает активное membership и текущие
подконтрольные группы при каждой операции. OWNER/ADMIN имеют область своей
организации, SUPERVISOR — только явно подконтрольные группы. Пустой набор
не включает обращения без группы. Членство, назначение и участие дают
независимые рабочие права, но не расширяют управленческую выдачу.

Общая область применяется к JSON/CSV/XLSX отчёту поддержки, результатам
клиентских оценок и анализу качества, включая прямые ID, корректировки,
исторические фильтры и ссылки на сообщения-основания. Смена роли, блокировка,
перенос обращения или отзыв контроля учитываются при следующей операции,
включая сервисный вызов с ранее созданным tenant-контекстом.

В обзоре `conversations/stats/` показатели, график, каналы и проблемные
обращения супервизора ограничены управленческой областью. Поля `waiting` и
`ops.waiting` остаются рабочим счётчиком очереди для существующего бейджа
чата: они используют обычную видимость и не исчезают при отзыве контроля,
если сохранились рабочие права. Для обычного сотрудника обзор сохраняет
прежнюю рабочую область; отчёт поддержки требует фильтр собственного ID.

Рабочее время и строки команды включают только текущих участников
подконтрольных групп. Числовые итоги считаются по разрешённым обращениям
один раз, даже если в прошлом отвечал сотрудник другой группы. Его ID в
деталях отчёта заменяется `null`.

В оценках `responderIds` и карточка `responders` ограничены текущей
разрешённой командой. Фильтр скрытого сотрудника возвращает пустой результат,
включая `count` и `scaleGroups`. Снимок фактически ответивших сотрудников
в БД сохраняется без изменений; удаление сотрудника из команды не удаляет
оценку и не меняет её шкалу или итоги.

В истории корректировок качества автор вне разрешённой команды возвращается
как `author: null`; собственная корректировка остаётся подписанной.
Значение, время, причина, номер ревизии и исходное заключение сохраняются.
Ссылка на сообщение проверяет текущую управленческую область, даже если
обычная рабочая видимость обращения сохранилась. Псевдонимизация AI и
клиентские/фоновые потоки не меняются.

JSON обзора и отчёта поддержки, результаты оценок, карточки и анализ имеют
`Cache-Control: private, no-store`; экспорты сохраняют такой же запрет кеша.
Это не отзывает уже скачанные файлы, но исключает повторную управленческую
выдачу из HTTP-кеша после изменения прав.

Контракты доменов: [отчёт поддержки](support-report-api.md),
[оценки клиентов](customer-ratings-api.md), [анализ качества](quality-analysis-api.md).

## Адресные проверки

Штатный запуск Skaro включает `backend-admin`; PostgreSQL и Redis должны
быть healthy. Команды выполняются с переменными окружения задачи.

```powershell
docker compose build backend-app backend-admin worker worker-events
docker compose exec -T backend-admin python manage.py check
docker compose exec -T backend-admin python manage.py makemigrations --check --dry-run
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/conversations/test_team_result_scope.py chatballs/conversations/test_support_report.py chatballs/conversations/test_support_work_status.py chatballs/conversations/quality/test_api.py chatballs/conversations/quality/test_results.py chatballs/ratings/test_results.py chatballs/ratings/test_ui_contract.py chatballs/identity/test_work_status_api.py chatballs/conversations/test_comment_public_effects.py
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/conversations/test_supervisor_access.py::SupervisorAccessTests::test_history_and_counters_do_not_disclose_inaccessible_dialogs
docker compose exec -T backend-admin python manage.py verify_support_exports
docker compose exec -T backend-app python manage.py verify_quality_runtime --organization-id 1
```

Новые проверки используют только штатную изолированную тестовую БД Django.
Проверка существующих экспортов выполняется в READ ONLY транзакции;
учётные данные, права и рабочие данные окружения не изменяются. Полный
набор, seed и браузерная проверка нового UI не требуются этой серверной задачей.

## Результат проверки 14.10.2026

Окружение `skaro-chatballs-t-139`: frontend `http://localhost:20004`, API
`http://localhost:20002`; PostgreSQL/Redis healthy, backend-admin доступен
внутри Compose. Штатная сборка backend-app/backend-admin/worker/worker-events,
Django check, отсутствие изменений миграций, Ruff и git diff --check прошли.
Все изменённые Python-файлы короче 300 строк.

Первый адресный прогон: 42 passed, четыре ошибки подготовки новых проверок
(диалоги создавались без обязательного контакта). После исправления запущены
только затронутые проверки: `test_team_result_scope.py`, проверка обзора из
`test_supervisor_access.py`, `ratings/test_results.py` и
`test_comment_public_effects.py`: 10 passed. Проверено 47 уникальных сценариев.

READ ONLY сравнение на существующей базе: 20 обращений, пять наборов фильтров,
JSON/CSV/XLSX совпали по значениям, единицам, полноте и деталям.
`verify_quality_runtime --organization-id 1` под runtime-ролью `chatballs_app`
вернул HTTP 200 для настроек и отчёта: 20 обращений, анализ выключен, работ нет.
Положительная выдача анализа, скрытие автора и отзыв ссылок проверены
адресными тестами в штатной тестовой БД, а не приписаны существующей базе.
