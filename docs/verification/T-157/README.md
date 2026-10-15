# T-157: проверка серверной библиотеки навыков

Проверено 15.10.2026 в штатном окружении `skaro-chatballs-t-157`,
которое запускает Skaro. Миграции `ai.0028_skill_library` и
`tenancy.0067_skill_library_guards` применились через штатный init.
Seed, bootstrap, смена паролей и подменные API не использовались.
Данные сценариев создавались только в отдельной БД pytest `test_chatballs`.

## Выполненные команды

Сборка backend-образа:

```powershell
docker compose build backend-app backend-admin
```

Успешно. Окружение повторно запущено через `start_environment` на текущих
исходниках. `docker compose ps` подтвердил backend-app, backend-platform,
backend-admin, PostgreSQL, Redis, frontend, web-chat и штатные воркеры.
Readiness через frontend `http://localhost:20004/api/v1/health/ready/`:
HTTP 200, `database=true`, `redis=true`. API: `http://localhost:20002`.
Публичный `GET /api/v1/webchat/skills/` вернул 404.

Проверка Django и состояния миграций:

```powershell
docker compose exec -T backend-admin python manage.py check
docker compose exec -T backend-admin python manage.py makemigrations --check --dry-run
```

Результат: `System check identified no issues`, `No changes detected`.
`compileall` новых серверных модулей завершился успешно. Ruff изменённых
Python-файлов с правилами проекта E/F/I/UP/B/DJ (кроме E501/DJ001) прошёл.
`git diff --check` прошёл.

Только затронутое поведение:

```powershell
docker compose exec -T backend-admin python -m pytest chatballs/ai/test_skills_api.py chatballs/ai/test_skills_access.py chatballs/ai/test_skills_rls.py chatballs/ai/test_skills_concurrency.py chatballs/i18n/tests.py::CatalogTests --reuse-db -q --tb=short
```

Результат финального запуска: `19 passed` за 86,64 секунды, включая
нулевые символы/некорректный Unicode и сохранность истории при удалении.
Полный набор проекта не запускался. Предупреждения относятся к существующей
миграции Django (`CheckConstraint.check`) и отсутствию staticfiles в dev.

## Покрытие требований

- Создание, чтение, полная атомарная замена, удаление; границы длины, пустой
  ввод, неизвестные поля, лимит тела, нулевые символы/некорректный Unicode,
  неизменность сохранённого при ошибках.
- Серверный поиск по обоим полям, страницы, метаданные/авторы и связи;
  отсутствие библиотеки в публичных маршрутах.
- Несколько агентов, повтор подключения, отдельное отключение, подтверждение
  удаления, конфликт устаревшего подтверждения и сохранность Message.
- OWNER/ADMIN; отказ EMPLOYEE/SUPERVISOR и чужой организации, включая сервисы.
- Реальная роль `chatballs_runtime_app`: полный HTTP lifecycle, RLS трёх
  таблиц, запрет чужих вставок/изменений, tenant FK, уникальность, отсутствие
  доступа без контекста и у platform. Проверено, что app не superuser,
  не BYPASSRLS и не член роли владельца схемы.
- Два параллельных создания с одним ключом дают один объект/аудит;
  две правки с одной ревизией дают одно сохранение и конфликт 409.
- Повтор PUT/POST не создаёт лишнюю ревизию/аудит; изменённое тело с прежним
  ключом отклоняется; удалённый объект не воссоздаётся повтором создания.
- Аудит сохраняет исполнителя, UUID, действие, ревизию и ID агентов,
  без содержимого инструкции; каталог RU/EN согласован.

## Границы и структура

UI и runtime AI не изменены; browser-проверка UI к этой задаче не относится.
Шаблоны пока принимаются только пустым списком: непустые отклоняются до
транзакции. Контракт расширяется проверкой и сохранением всего набора
шаблонов в одной транзакции будущей задачей.

Проверены SRP, separation of concerns и размеры всех изменённых Python-файлов:
модели, запросы/сериализация, валидация, сервисы и HTTP разделены. Максимум
нового файла — 132 строки; затронутого существующего — 283. Файлов свыше
300 строк нет.
