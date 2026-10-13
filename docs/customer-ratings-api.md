# Клиентская оценка завершённого обращения

Самостоятельный backend SPEC-0032, без нового UI. Решения владельца для первого
выпуска: шкала 1–5, транспорт WEB, срок credential — семь суток после отправки;
обычный оператор не получает результаты. Клиентская форма, настройки и карточка
ожидают отдельного утверждённого baseline.

## Настройки

`GET/PATCH /api/v1/organizations/{organization_public_id}/ratings/settings/`
доступен только активным OWNER/ADMIN. Исходное состояние:

```json
{"enabled": false, "scale": [], "text": "", "delaySeconds": 0}
```

Администратор задаёт `scale` как пять объектов `{"value": 1, "label": "..."}`
с целыми значениями 1–5 в этом порядке и непустыми подписями до 120 символов.
Подписи и текст вводятся на языке организации; встроенного клиентского шаблона
нет. Текст ограничен 4000 символами, задержка — целыми секундами от 0 до 604800.
Включение требует полной шкалы и непустого текста. Изменение настройки
аудируется без текста и credential. Выключение окончательно отменяет ожидающие
запросы; повторное включение не восстанавливает их и не оценивает старые CLOSED.

## Планирование и WEB-доставка

Запись штатного CLOSED планирует запрос внутри транзакции завершения, включая
фоновое закрытие. One-to-one связь с фактом завершения защищает от повтора.
PostgreSQL фиксирует шкалу, текст, задержку, срок отправки и сотрудников:
PUBLIC_REPLY/HUMAN до завершения плюс существующие публичные сообщения
OPERATOR до завершения, включая сообщения до границы журнала. AI, системные записи, назначение и участие сами
по себе в снимок ответивших не входят. Исторические факты сохраняют сотрудника
после удаления membership; отсутствующий старый автор не восстанавливается.

WEB-адаптер привязывает запрос к исходной WebSession по подключению, контакту
и `webChatWidgetId`. Штатный poller `run_worker --role poller` проверяет запросы
каждый цикл опроса, не раньше `due_at`. Перед отправкой проверяются настройка,
существование исходной сессии, её срок, опубликованный виджет, активное
подключение и агент. Недоступный транспорт/сессия отменяют запрос. Другие
транспорты и нативные кнопки в этом выпуске не поддерживаются.

Отправка для WEB означает атомарную публикацию запроса для поллинга сессии,
а не подтверждение просмотра человеком. В существующем ответе
`GET /api/v1/webchat/messages/` добавлено поле `ratingRequests`, доступное и
после CLOSED, когда нового открытого диалога ещё нет. Каждый элемент содержит
`credential`, `text`, `scale`, `expiresAt`. Повтор поллинга возвращает тот же
логический запрос с тем же credential. После ответа или истечения он исчезает.
Штатный новый клиентский ответ по-прежнему создаёт связанный новый диалог.
Оценка не создаёт Message, не вызывает AI и не переоткрывает обращение.

Токен выводится HMAC-SHA256 из случайного UUID запроса и секрета установки;
хранится только SHA-256 verifier, без токена в сообщениях, outbox или логах.
При смене секрета ранее выданный токен остаётся действительным по verifier,
но старый токен больше не восстанавливается для WEB-поллинга. Новые запросы
используют новый секрет. Клиентская форма должна передавать токен заголовком,
не помещая его в URL/path/query или журналы. HTML-форма в этой задаче не создаётся.

## Ограниченный публичный API

`GET/POST /api/v1/ratings/`, только `Authorization: Bearer <credential>`.
Прямых идентификаторов запросов или организаций этот API не принимает.
GET возвращает только `text`, `scale`, `expiresAt`, `commentMaxLength`, `result`.
В нём нет переписки, контакта, сотрудников и внутренних идентификаторов.
Ответы имеют `Cache-Control: no-store`, `Referrer-Policy: no-referrer`.

POST принимает `{"value": 5, "comment": "..."}`: только целое значение снимка
и необязательный строковый комментарий до 2000 символов. Лишние поля, boolean,
строковые числа и null-комментарий отклоняются. Первый ответ — 201; точный
повтор значения и комментария — 200 с прежним результатом и серверным временем;
изменение любого из них — 409. Credential отсутствующего, отменённого,
удалённого или просроченного запроса — 404. Лимиты штатного DRF/cache:
60 запросов/минуту по IP и 10/минуту по SHA-256 credential, при превышении — 429.

Приём блокирует запрос в tenant-транзакции, запись оценки уникальна и
неизменяема также в PostgreSQL. RLS принудителен для всех трёх таблиц;
platform-роль не получает доступа. Security-barrier каталог разрешает только
маршрут по verifier действующего запроса. Физическое удаление обращения
каскадно удаляет запросы/ответы и закрывает credential.

## Карточка и отчётный источник

`GET /api/v1/organizations/{organization_public_id}/ratings/conversations/{id}/`
возвращает `results` для карточки. `GET .../ratings/results/` возвращает
`count`, `results`, `scaleGroups`. Доступ: активные OWNER/ADMIN — организация;
SUPERVISOR — только текущие подконтрольные группы. Обычное членство, назначение
и участие область отчёта не расширяют. Отзыв контроля или перенос обращения
применяется и к ранее полученным результатам.

Фильтры отчёта: `responderId`, текущий `groupId`, `after` (включительно),
`before` (исключительно), `offset`, `limit` (1–100, исходно 50). Время фильтрации
— время получения оценки. Идентификатор чужого сотрудника/группы не раскрывает
чужие totals. Результат содержит `id`, `requestId`, `conversationId`,
`completionId`, `responderIds`, снимок `scale`, `value`, `comment`, `receivedAt`.
Credential в защищённых результатах тоже отсутствует.

`scaleGroups` содержит SHA-256 точного снимка шкалы, сам снимок, количество
оценок и распределение по значениям. Одна оценка учитывается один раз,
независимо от числа ответивших; среднее и автоматическая нормализация отсутствуют.
Изменённые подписи сохраняют отдельную группу шкалы. Сервер допускает выдачу
старых снимков отдельно, даже если будущий выпуск расширит набор шкал.

Первичный приём атомарно записывает outbox-событие `ratings.received` с
`aggregate_type=CustomerRating`, `aggregate_id` и payload `{"ratingId": id}`.
Повтор ответа второго события не создаёт. Событие не содержит комментария,
credential или персональных данных; потребитель отчётов обязан загрузить
источник в tenant-контексте и применить текущую область доступа. Существующая
статистика диалогов не смешивает эти результаты со своими показателями.

## Проверка

В окружении Skaro после `start_environment`:

```powershell
docker compose exec -T backend-admin python manage.py check
docker compose exec -T backend-admin python manage.py makemigrations --check --dry-run
docker compose exec -T backend-admin pytest -q --reuse-db chatballs/ratings chatballs/i18n/tests.py::CatalogTests chatballs/conversations/test_domain_event_sources.py::DomainEventSourceTests::test_assignment_claim_queue_close_and_retries chatballs/conversations/test_domain_event_sources.py::DomainEventSourceTests::test_background_close_is_system_and_no_duplicate chatballs/conversations/test_domain_event_sources.py::DomainEventSourceTests::test_inbound_queue_followup_and_dedup chatballs/conversations/test_domain_event_sources.py::DomainEventSourceTests::test_services_run_under_runtime_tenant_role chatballs/webchat/tests.py::PublicWebChatWidgetTests::test_voice_message_round_trip chatballs/webchat/tests.py::PublicWebChatWidgetTests::test_file_message_round_trip chatballs/webchat/tests.py::PublicWebChatWidgetTests::test_deleted_conversation_resets_widget_thread chatballs/webchat/tests.py::PublicWebChatThrottlingTests::test_polling_is_not_starved_by_the_send_limit
```

`--create-db` требуется при первом прогоне изменённой схемы; при неизменной
схеме повторные относящиеся проверки выполняются с `--reuse-db`. Полный набор,
seed и изменение существующих аккаунтов для этой проверки не требуются.
