# Проверка T-159

Штатное окружение Skaro: `skaro-chatballs-t-159`. Frontend
http://localhost:20010, backend http://localhost:20008. Frontend использует
`VITE_DEV_API_TARGET=http://backend-app:8000`; readiness проверяет PostgreSQL
и Redis. Добавлен предусмотренный compose сервис backend-admin для тестов.
Сервисы запускаются/пересобираются через `start_environment`; init применяет
миграции. Никаких seed, сброса доступа или подменного API не запускалось.

## Исполняемые проверки

```powershell
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/ai/test_skill_template_language.py chatballs/ai/test_skill_template_security.py chatballs/ai/test_skill_template_limits.py chatballs/ai/test_skills_templates_api.py chatballs/ai/test_skills_api.py chatballs/ai/test_skills_access.py chatballs/ai/test_skills_concurrency.py chatballs/ai/test_skills_rls.py chatballs/i18n/tests.py::CatalogTests
docker compose exec -T backend-admin python -m compileall -q chatballs/ai/skill_templates chatballs/ai/skills_models.py chatballs/ai/skills_json.py chatballs/ai/skills_preview.py chatballs/ai/skills_views.py chatballs/ai/skills_validation.py chatballs/ai/skills_queries.py chatballs/ai/skills_urls.py chatballs/i18n/formatting.py
docker compose exec -T backend-admin python manage.py check
docker compose exec -T backend-admin python manage.py makemigrations --check --dry-run
ruff check apps/backend/chatballs/ai/skill_templates apps/backend/chatballs/ai/skills_models.py apps/backend/chatballs/ai/skills_queries.py apps/backend/chatballs/ai/skills_urls.py apps/backend/chatballs/ai/skills_validation.py apps/backend/chatballs/ai/skills_views.py apps/backend/chatballs/ai/skills_preview.py apps/backend/chatballs/ai/skills_json.py apps/backend/chatballs/ai/test_skill_template_language.py apps/backend/chatballs/ai/test_skill_template_security.py apps/backend/chatballs/ai/test_skill_template_limits.py apps/backend/chatballs/ai/test_skills_templates_api.py apps/backend/chatballs/i18n/formatting.py apps/backend/chatballs/i18n/messages/skills_ru.py apps/backend/chatballs/i18n/messages/skills_en.py
git diff --check
```

Полный набор проекта не запускался. Начальные прогоны выявили и помогли
исправить смену прежнего кода ошибки инструкции и чтение тела после session/CSRF.
В проверках используются только тестовая БД pytest и штатные роли PostgreSQL;
тестовые организации не устанавливаются в работающую базу приложения.

Окончательный прогон: **39 passed**, 159.77 s; полный вывод — [pytest.txt](pytest.txt).
Предупреждения относятся к существующей миграции с deprecated CheckConstraint
и отсутствующему каталогу collectstatic в dev. Компиляция Python завершилась
с кодом 0, `manage.py check` — без замечаний, `makemigrations --check --dry-run`
— No changes detected; Ruff и `git diff --check` прошли. Миграция
`ai.0029_skill_templates` отмечена применённой в `showmigrations ai`.

После временных тайм-аутов автоматического readiness проверка повторена через
Skaro на окончательных исходниках: `start_environment` подтвердил running and
ready. Прямой readiness вернул database=true/redis=true. Пересоздание контейнеров
прервало один промежуточный прогон; он не засчитывался. Окончательные тесты
выполнены после завершения запуска, без параллельного пересоздания сервисов.

После первого submit_result Skaro отметил все 9 критериев, но обнаружил
пересечение вставок в начале skills_ru/en с ключом model_unsupported из main.
Без слияния веток новые ключи этой задачи переставлены в конец словарей.
AST-сравнение подтвердило неизменность всех 49 ключей и значений каждой локали.
Повторно запущены только затронутые CatalogTests с `--reuse-db`: **5 passed**,
15.96 s; [вывод](catalog-recheck.txt). Ruff и `git diff --check` также прошли.

## Браузерная проверка документов обработчика

Playwright MCP задачи, существующий demo ADMIN, штатные login/session/CSRF.
Наличие аккаунта сначала проверено read-only в копии БД; учётные данные не
менялись. GET `skills/bases/orders/`, затем POST `skills/preview/` для всех
четырёх примеров. Все ответы 200; число/значения позиций и суммы берутся из
ответа настоящего API. Для просмотра в браузере временно создан iframe с
полученным **srcDoc**, `sandbox=""`, `referrerpolicy="no-referrer"`.
Это техническая проверка серверного документа, не реализованный редактор
навыков и не новый продуктовый экран.

| Документ | Строки | Высота при 300 / 340 | scrollWidth при 300 / 340 |
| --- | --- | --- | --- |
| Короткий заказ | 2 | 177 / 177 | 300 / 340 |
| Длинный заказ | 7 | 472 / 472 | 300 / 340 |
| Статус со сроком | 0 | 107 / 107 | 300 / 340 |
| Статус без срока | 0 | 72 / 72 | 300 / 340 |

Повторено на светлой и тёмной подложке (16 вариантов). Нет горизонтального
переполнения; длинное название переносится, суммы остаются справа. DOM без
eta не содержит блока срока и иконки часов; текст тоже не содержит строки срока.
Счётчик показывает форму «позиции» для 2 и «позиций» для 7; значение счётчика
формируется CSS по строкам. Визуально просмотрены сохранённые изображения:

- [Заказ, 300](order-long-300.png)
- [Заказ, 340](order-long-340.png)
- [Статус без срока, 300](status-no-eta-300.png)

Для проверки изоляции отправлен несохранённый CSS `body{background:red}
.card{color:blue}`: внутри frame фон красный/текст синий, фон оболочки остаётся
`rgb(20,20,20)`, `iframe.contentDocument === null`, sandbox пустой. Данные и
конфигурация при этой проверке не сохранялись. Изоляция обеспечивается отдельным
документом и sandbox, а не префиксом CSS-селектора.

## Проверка структуры и границ задачи

Проверены SRP/NO GOD FILES: схема, язык, лимиты, HTML, структура блоков, CSS,
изоляция, сборка результата и основа разделены на модули. Новые исходники меньше
300 строк; интерфейсных компонентов нет. Серверные источники карточек созданы
по утверждённому `design/baseline/agent-skills/Оформленные сообщения.dc.html`
основной копии; карточка заказа не зашита в React.

Runtime и предпросмотр вызывают один `render_template`; интеграция в ход AI,
сохранение снимков Message, доставка и общий продуктовый renderer остаются в
соответствующих задачах этапа. Текущая задача не заявляет эти UI/runtime-задачи
реализованными. Контракт потребителя изолированного документа описан в
[API обработчика](../../skill-templates-api.md).
