# T-158: инструкционные навыки в общем ходе агента

Проверено 15.10.2026 в штатном окружении Skaro
`skaro-chatballs-t-158`. Источники — worktree задачи; PostgreSQL и Redis
штатные. `backend-admin` добавлен через `configure_environment`, окружение
после изменений запускалось через `start_environment` с обычным init.
Seed, bootstrap, сброс учётных данных и подменные API в окружении не применялись.
Тестовые записи существуют только в отдельной БД pytest `test_chatballs`.

## Сборка и системные проверки

```powershell
docker compose build backend-app backend-admin
docker compose exec -T backend-admin python manage.py check
docker compose exec -T backend-admin python manage.py makemigrations --check --dry-run
```

Сборка успешна; Django: `System check identified no issues`, миграции:
`No changes detected`. Зависимости и схема БД не менялись.
Ruff всех изменённых/новых Python-файлов по правилам проекта E/F/I/UP/B/DJ
прошёл; `git diff --check` прошёл.

`docker compose ps` подтвердил backend-app, backend-platform, backend-admin,
PostgreSQL, Redis, frontend, web-chat и воркеры. Readiness через frontend
`http://localhost:20004/api/v1/health/ready/` вернул HTTP 200,
`database=true`, `redis=true`. Frontend использует штатный proxy
`VITE_DEV_API_TARGET=http://backend-app:8000`, API задачи —
`http://localhost:20002`, platform — `http://localhost:20003`,
web-chat — `http://localhost:20005`.

## Только затронутое поведение

```powershell
docker compose exec -T backend-admin python -m pytest chatballs/ai/test_skill_snapshot.py chatballs/ai/test_skill_loop.py chatballs/ai/test_skill_chat.py chatballs/ai/test_test_chat.py chatballs/ai/test_turn_pseudonymization.py chatballs/ai/test_tool_support.py chatballs/ai/test_diagnostic_capture.py chatballs/ai/test_tool_loop.py::TurnDeadlineTests chatballs/ai/tests.py::ChatInvocationTests chatballs/conversations/test_ai_turn.py::AiTurnQueueTests chatballs/i18n/tests.py::CatalogTests --reuse-db -q --tb=short
```

Результат: **71 passed** за 243,79 секунды. Полный набор проекта не запускался;
одновременных прогонов на одной БД не было. Предупреждения относятся к
существующей миграции Django (`CheckConstraint.check`) и отсутствию
`staticfiles/` в dev.

После финального уточнения фильтров организации при фиксации ответа backend
снова собран и окружение перезапущено через Skaro. Повторены непосредственно
затронутые сценарии завершения живого хода:

```powershell
docker compose exec -T backend-admin python -m pytest chatballs/ai/test_skill_chat.py chatballs/conversations/test_ai_turn.py::AiTurnQueueTests --reuse-db -q --tb=short
```

Результат на окончательных исходниках: **11 passed** за 109,08 секунды.
Повторные Ruff, `git diff --check` и readiness также успешны.

| Критерий | Проверка |
| --- | --- |
| 1 | `SkillSnapshotTests`: каталог содержит только id/name/description, полные инструкции отсутствуют в начальном запросе и repr плана; выбранная инструкция приходит отдельным результатом загрузки. Модель шаблонов/примеров не читает. |
| 2 | `SkillSnapshotTests`: одинаковый отказ для чужого/неподключённого/неизвестного ID; настоящая роль app видит только свою организацию. Другая DB connection меняет и отключает навык при живом снимке; текущая инструкция остаётся прежней, следующий план видит новое состояние. Загрузка не делает запросов к БД, удаление тоже не меняет снимок. |
| 3 | Проверены занятые HTTP/MCP-имена и выбор свободного внутреннего суффикса. `SkillChatTests` проверяет неизменность английской директивы, протокола передачи, ограничений и списка разрешённых инструментов. |
| 4 | `SkillLoopTests`: пять раундов и заключительный ответ, повторные ошибки выбора, отказ модели соблюдать запрет, лимит пакета и аргументов, общий объём и нехватка места даже для ошибки, истёкший срок. Таймаут провайдера и backoff ограничены остатком срока; поздний ответ учитывается, но не доставляется. |
| 5 | `SkillChatTests`: одинаковая загруженная инструкция в живом и проверочном чате; реальная роль app; ноль Contact/Conversation/Message/OutboxEvent/TurnDiagnostic после проверки. Существующий кеш совместимости даёт supported/unsupported/unknown; отказ не подменяется полным текстом. Дополнительно исправлена короткая RLS-транзакция проверки прав существующего test-chat. |
| 6 | `SkillLoopTests`, `SkillChatTests` и регрессии псевдонимизации/диагностики: каталог, инструкция, значения с кавычками и описания схем маскируются одной картой; JSON Schema остаётся пригодной, замаскированный UUID восстанавливается. Исходных персональных значений в запросах/диагностике/учёте нет. Учтены все раунды, внутренние загрузки не создают ToolCallRecord/плашки; у смешанного сценария в следе только HTTP. |
| 7 | «Уточнение обращения» без шаблонов: выбор → загрузка → запрос номера, два раунда, точный расход токенов. Проверены обычный агент, передача сотруднику, перехват до хода и во время загрузки, повтор события и HTTP-привязки. При перехвате в сетевой фазе ответ отбрасывается, расход сохраняется. |
| 8 | Этот протокол, контракт `docs/agent-skills-runtime.md`, сборка, Django/migrations, Ruff, целевые тесты с --reuse-db и проверка структуры. UI не изменён, browser-проверка нового UI не применяется. |

## Границы проверки

В скопированных данных установки доступны только штатные DEMO-провайдеры.
Сценарии runtime в pytest используют существующий ScriptedProvider в памяти
для воспроизводимого выбора операций; никакой HTTP/MCP-сервер-заглушка не
создавался. Это проверка протокола и ограничений, а не оценка качества выбора
навыка внешней LLM. Настройки и credentials провайдера не подменялись ради
ручной демонстрации. UI библиотеки/подключений, шаблоны и их доставка —
последующие задачи этапа.

## SRP / NO GOD FILES

Ответственности разделены: `turn_skills` — снимок и загрузка;
`operation_masking` — схемы; `chat_execution` — сетевой вызов и retry deadline;
`turn_types` — структуры; `tool_loop` — общий цикл;
`ai_turn_completion` — фиксация после проверки текущего управления.
Оркестратор `ai.turn` — 256 строк, `conversations.ai_turn` — 285.
Изменённых Python-файлов длиннее 300 строк нет. Новых экранов, компонентов,
стилей и отступлений от design baseline нет.
