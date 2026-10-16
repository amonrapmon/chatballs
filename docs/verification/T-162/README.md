# T-162: редактор схемы и шаблонов

Проверено 16.10.2026 в штатном окружении задачи, frontend :20004 → backend-app :8000 внутри Compose. `/api/v1/health/ready/` подтвердил PostgreSQL и Redis. Через backend-admin подтверждён уже установленный демо-набор и существующий ADMIN; вход выполнен существующими данными. Seed, сбросы, подмена API и временные серверы не использовались. Объекты проверки созданы обычными действиями редактора в копии данных задачи.

## Исполняемые проверки

Все команды запускались из корня worktree после `start_environment` на текущих исходниках.

```powershell
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run build
docker compose exec -T frontend npm --workspace @chatballs/internal-ui test -- src/features/skills/template-editor/schema.test.ts src/features/skills/template-editor/schemaOrder.test.ts src/features/skills/template-editor/model.test.ts src/features/skills/model.test.ts src/features/skills/presentation.test.tsx
docker compose exec -T frontend npm --workspace @chatballs/ui run typecheck
docker compose exec -T frontend npm --workspace @chatballs/ui test -- src/messages/PreparedMessage.test.tsx
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/ai/test_template_editor_diagnostics.py chatballs/ai/test_skills_templates_api.py chatballs/ai/test_skill_template_language.py chatballs/ai/test_skill_template_security.py chatballs/ai/test_skill_template_limits.py chatballs/i18n/tests.py::CatalogTests
docker compose exec -T backend-admin ruff check chatballs/ai/skill_templates/engine.py chatballs/ai/skill_templates/errors.py chatballs/ai/skill_templates/language.py chatballs/ai/skill_templates/order_basis.py chatballs/ai/skill_templates/schema.py chatballs/ai/skills_preview.py chatballs/ai/test_template_editor_diagnostics.py chatballs/i18n/messages/skills_ru.py chatballs/i18n/messages/skills_en.py
git diff --check
```

Результат: build успешен (обычное предупреждение Vite о крупном chunk); 13 frontend + 3 renderer + 31 backend тест прошли; typecheck и Ruff прошли. Полный набор не запускался. Выводы сохранены рядом: `build.txt`, `frontend-tests.txt`, `renderer-tests.txt`, `backend-tests.txt`, `ui-typecheck.txt`, `ruff.txt`. Установленные зависимости сопоставлены с lockfile: расхождений нет (`dependencies.txt`); выполнен npm ci (`npm-ci.txt`).

## Browser-проверка

Task-local Playwright, штатный backend; окно 1440×900, дополнительно 1024×900. Исходный baseline открыт в браузере, кадры сохранены как `baseline-t1`…`baseline-t4` в обеих темах. Сравнение сохраняет три колонки, иерархию, отступы вложенных полей, вкладки, панель примера и предпросмотра. Служебная рамка baseline в продукт не переносилась. Поставляемые безопасные исходники T-159 остаются обычным редактируемым шаблоном.

| Критерий | Проверка и результат | Кадры |
|---|---|---|
| 1 | HTML/CSS/Текст, Виджет/Текст, 340/300; код в CodeMirror, результат только от сервера; новый пустой шаблон без данных заказа. С нуля создано «Приветствие» с полем name, HTML и текстом, сохранено и прочитано из API. | t1-light/dark, css-dark, new-template-light-en, universal-preview-light-en |
| 2 | Modal поля: объект extra, вложенное boolean flag, редактирование, удаление объекта с подтверждением детей. qty → quantity не переписывает исходники: ошибки обеих вкладок и примера; возврат имени устраняет ошибки. Циклы, неизвестный/скалярный родитель, перенос и вложенные списки проверены schema.test.ts; порядок сохраняется после JSONB/API. | field-object-dark, field-delete-children-dark, field-rename-validation-dark |
| 3 | Короткий/длинный и со сроком/без срока проходят реальный серверный preview. В JSON меняли значения. Первый preview-запрос задержан Playwright route, затем пропущен в настоящий backend без замены ответа: «Старый» не заменил уже показанный «Новый». Backend-тест сравнивает preview со снимком рабочего renderer. Общий PreparedMessage из packages/ui получает только подготовленный ответ; видимый iframe имеет sandbox="", оба iframe без allow-scripts. | universal-preview-light-en, t1-long-* |
| 4 | Одновременно qty='два', отсутствующий total, неизвестный discount и незакрытый each: диагностика в схеме/строках/вкладках/сводке, сохранение конфигурации блокировано. Временный JSON «{» блокирует preview, сохранение валидной конфигурации успешно; сырой ввод остаётся. Backend проверяет все ошибки одним ответом и отсутствие записи при preview. | t2-light/dark, temporary-example-light |
| 5 | Семь позиций длинного примера при 300/340, итог 93 100, нет горизонтального скролла карточки. Без eta отсутствует вся строка, текст «Заказ № 4512\nСтатус: Ожидает примерки», без тире. При 1024 document.scrollWidth = innerWidth = 1024, панель preview 362 px вмещает ширину 340. | t1-long-300/340-light/dark, t3-light/dark, status-no-eta-widget-dark, editor-1024-light |
| 6 | Save Template одним PUT записал одновременно description и text, revision 11→12; показано «Будут сохранены и изменения навыка». Сохранение из K5 и T4 использует тот же набор. Пустое имя вернуло к ошибке родителя, код сохранился при повторном открытии. Offline: Save и T4 Save оставили форму/Modal и код, после восстановления сети повтор успешен. Конкурирующий настоящий PUT revision 7→8 вызвал 409 локального сохранения; код сохранился, отмена обновления сохранила его, замена по подтверждению загрузила серверное. «Остаться»/«Не сохранять» T4 проверены, локальный возврат оставляет изменения до публикации. | atomic-save-light, parent-invalid-dark, save-failure-dark, conflict-dark, t4-light/dark, t4-failure-dark |
| 7 | Установка основы заполняет локальную форму и два изменяемых шаблона, создание через Save Template атомарно создаёт навык. После переключения профиля RU→EN названия, описания, примеры и исходники установленного навыка остались RU; системные подписи EN. Профиль возвращён к RU/light. | t1-basis-unsaved-light, t3-light-en, new-template-light-en |
| 8 | Обе темы сверены с baseline; только согласованные дополнения docs/agent-skills-ui-agreement.md. Целевые проверки перечислены выше. SRP/NO GOD FILES проверен по ответственности и размерам. | structure.txt, baseline-*, все продуктовые кадры |

Сетевые ошибки в консоли при offline и ответы 400/409 в отрицательных сценариях ожидаемы; после восстановления и перезагрузки успешные preview работают без ошибок консоли. Медленная холодная загрузка frontend ожидалась до готовности реального приложения.

## Разделение ответственности

SkillEditor и TemplateEditor компонуют подвиды. Состояние/атомарное сохранение — useSkillDraft; локальный сырой JSON — useTemplateSession; debounce/отмена/поколение preview — useTemplatePreview. Схема и порядок — отдельные чистые модели; Modal, исходники, JSON и preview — отдельные компоненты. PreparedMessage — единственный общий renderer подготовленных снимков для последующего использования в ленте. Сервер продолжает применять существующий безопасный compiler; дополнены агрегирование и локализация диагностик, порядок полей и метаданные примеров.

Все новые компоненты меньше 180 строк, новые/изменённые функциональные модули меньше 300. Крупные существующие агрегаторы RU/EN получили только импорт и spread отдельного каталога. Перечень размеров — structure.txt. Новых экранов или визуального конструктора нет.
