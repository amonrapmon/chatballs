# T-161 — финальный ответ и снимок доставки

Контракт: [agent-reply-snapshots.md](../../agent-reply-snapshots.md).
Изменения ограничены серверным workflow, контрактами TypeScript и документацией;
продуктовые экраны, макеты, HTML/CSS основы заказов не менялись.

## Окружение

Штатное окружение Skaro `skaro-chatballs-t-161`, копия данных основной установки.
Через configure_environment к прежнему запуску добавлен документированный
backend-admin без нового host-порта. Запуск, сборка образов и миграции —
только start_environment. Прямой readiness рабочего места подтвердил
database=true и redis=true; compose ps показал здоровые PostgreSQL,
Redis, backend-app и backend-platform, работающие frontend/web-chat/workers.

- Рабочее место: http://localhost:20010
- API: http://localhost:20008
- Виджет: http://localhost:20011

Первый запуск не прошёл healthcheck backend-app во время reload исходников;
повторный start_environment подтвердил готовность. Миграция
conversations.0047_message_reply_snapshot применена штатным init.
Учётные данные не менялись, seed и подменные сервисы не запускались.
Тестовые записи/провайдеры и подмена внешней отправки используются только
в изолированной БД pytest, не в рабочей базе и не для демонстрации интерфейса.

## Выполненные проверки

```powershell
docker compose exec -T frontend npm run build --workspace @chatballs/internal-ui
docker compose exec -T web-chat npm run build --workspace @chatballs/web-chat
docker compose exec -T backend-admin python manage.py check
docker compose exec -T backend-admin python manage.py makemigrations --check --dry-run
docker compose exec -T backend-admin python manage.py showmigrations conversations --plan
docker compose exec -T backend-admin pytest -q --reuse-db --tb=short chatballs/ai/test_template_completion.py chatballs/ai/test_template_realtime.py chatballs/ai/test_turn_templates.py
```

Обе production-сборки (tsc + Vite) завершились с кодом 0. Предупреждение
Vite о размере существующих chunks не блокирует сборку. Django check —
без замечаний; makemigrations — No changes detected; миграция снимка отмечена [X].
Новый целевой набор: **17 passed**, 78.20 s. Он проверил типы и токены,
восстановление перед HTML-очисткой, ограниченный цикл, выбор одного ответа,
неизменяемость плана/сообщения, текстовые транспорты/почтовое продолжение,
повторы, перехват/отмену/срок, передачу человеку, RLS-роль, публичную изоляцию,
проверочный чат без клиентских сущностей и WebSocket-инвалидацию с REST-чтением.

Также выполнялся только затронутый прежний набор:
test_skill_loop.py, test_skill_snapshot.py, test_skill_chat.py и test_ai_turn.py:
**28 passed** в совместном прогоне. Первые новые тесты в том прогоне упали
из-за пропущенного organization при создании тестового Conversation;
setup исправлен. Следующая проверка выявила слишком широкое утверждение
об отсутствии слова data в диагностике: схема операции вправе содержать это
поле. Проверка уточнена до отсутствия аргументов/результатов; новый набор прошёл.
Полный набор проекта не запускался.

После окончательных изменений диагностики и повторного start_environment
выполнен дополнительный целевой набор (**19 passed**, 110.18 s):

```powershell
docker compose exec -T backend-admin pytest -q --reuse-db --tb=short chatballs/ai/test_turn_templates.py chatballs/ai/test_template_completion.py::TemplateCompletionTests::test_snapshot_survives_delete_and_retry_uses_saved_reply chatballs/ai/test_template_completion.py::TemplateCompletionTests::test_live_template_runs_with_runtime_tenant_role chatballs/ai/test_template_realtime.py chatballs/conversations/test_ai_turn.py chatballs/conversations/test_email_transport.py::EmailSendTests chatballs/webchat/test_site_field_events.py::SiteFieldEventTests::test_site_field_events_are_not_sent_to_customer_widget
```

Вывод: [final-checks.txt](final-checks.txt). Предупреждения — существующая
deprecated-форма CheckConstraint и отсутствие collectstatic в dev.

Ruff по всем изменённым Python-файлам, проверка синтаксиса через compile()
и git diff --check прошли. SRP/NO GOD FILES: максимальная длина изменённого
исходника — 290 строк (conversations/ai_turn.py); подготовка, неизменяемые
данные ответа, диагностика, доставка и сериализация разделены.

## Проверка готового навыка без внешних доступов

Владелец явно указал закрыть задачу БЕЗ РЕАЛЬНЫХ ДОСТУПОВ. Поэтому живой
вызов системы заказов исключён из приёмки и не заявляется выполненным.
Общий путь проверочного чата и отсутствие клиентских записей подтверждены
тестами; реальный источник заказов в копии отсутствует.
Read-only проверка Integration(kind=EXTERNAL_SERVER) и AgentTool в tenant_atomic
для всех четырёх организаций копии вернула пустые списки.
Для согласованной проверки добавлен test_order_template_runtime.py: встроенная
основа проходит общий runtime и явно разрешённый HTTP-инструмент; сетевой вызов
заменён ответом только внутри pytest, без запуска API/серверов. Значения карточки
и статуса берутся из результата инструмента, не из примеров редактора.
Отсутствующий инструмент не вызывается; недостаток обязательных данных ведёт
к передаче человеку без снимка. Примеры не подменяют источник в работающем чате.

```powershell
docker compose exec -T backend-admin pytest -q --reuse-db --tb=short chatballs/ai/test_order_template_runtime.py
```

Окончательный результат: **2 passed**, 59.23 s;
[order-checks.txt](order-checks.txt). Исходная проверка отсутствия срока была
уточнена до CSS-класса блока: строка eta также встречается внутри details.
Браузерная демонстрация внешней системы и реальные внешние вызовы не выполнялись,
как прямо указал владелец; это ограничение проверки, а не скрытая подмена сервиса.
