# Connector Native Mirroring · план реализации и аудит паритета

> Для исполнителей: superpowers:subagent-driven-development. Основание — задание владельца «Native Mirroring для API Connector и вывод Legacy Gateway из эксплуатации» и согласования от 19.11.2026.

**Цель** — перевести TG/MAX Native Mirror на API Connector и определить, когда можно убрать Legacy Gateway из рантайма.

**База аудита** — Chatballs `eba2d6bb36d3b0d051f8c3f146573acb166414bc`, Green Adapter `0f9a54ce038efda5f5ac6a026cf0617b83821f02`. Оба PR направляются в `main` репозиториев amonrapmon. Production, учётные данные и история миграций вне задачи.

## Матрица паритета до изменений

| Поведение | Gateway | API Connector на main | Проверка целевого поведения |
| --- | --- | --- | --- |
| Настройка | `native_mirror_mode` в config, ENABLED или исторические режимы | Нет пользовательского opt-in, валидное событие сразу обрабатывается | Новый Connector выключен, PATCH/GET, audit, отсутствие перезапуска, сохранение transport/media |
| TG/MAX native outbound | `outgoingMessageReceived` после точной корреляции, raw event и retry | Reconciliation есть, четыре entry points не задают `operatorMirror` | Fastify → raw event → lease/retry → реальный Connector HTTP, обе платформы и два независимых источника |
| Свой исходящий | Собственный provider ID исключается, есть status projection | Connector echo и receipt в Chatballs для оператора, у адаптера корреляция плюс receipts | Точные совпадения не создают внешнее сообщение, неоднозначность не разрешается по тексту |
| Идентичность и текст | Источник/tenant, provider ID, timestamp, reply ID, service account | Источник/tenant, provider ID, neutral author, text; timestamp только валидируется, quote отклоняется | Origin без локального сотрудника, stable IDs, реальное время и reply ID в Message |
| Диалог и replay | Выбирает единственный открытый диалог, durable receipt/replay при missing/ambiguous | Последний открытый диалог, unknown → 409 с retry у отправителя; provider dedup в пределах выбранного диалога | Источник + чат + provider ID, включая повтор после переоткрытия; неизвестный диалог не создаётся |
| AI supersession | Ревизия, завершение активных ходов, неизменный control mode, claim перед первым Gateway HTTP | Принудительный операторский ingress и PAUSED для исходящего наблюдения; Connector delivery только для OPERATOR | Новая ревизия под блокировкой диалога, in-flight и queued AI отменяются, новый входящий может начать ход при включённом AI |
| Media | Нативное зеркалирование личного текста; вложения вне старого потока | Обычные ingress/command media работают; observed media вне контракта | Unsupported observed media зафиксированы в durable raw с диагностикой, обычный media lifecycle сохранён |
| VK Native Mirror | Собственный VK adapter, receipt, ревизия, взаимная блокировка с local send | Не зависит от Connector | Существующие VK проверки |
| Legacy Gateway | Самостоятельные URL, delivery/runtime, UI, config, поля и миграции | Прямой runtime ещё присутствует | Запретить создание; существующие связи и данные сохранить до миграции и доказательства паритета |

## Контракт

- Настройки Integration в `config`: `mirrorExternalOutgoingEnabled` и `connectorAiOutboundEnabled`, оба boolean, отсутствующее значение означает false. Штатный `integrations.manage` проверяется на сервере. Согласован существующий `SwitchButton` в форме под выбором сервиса и отдельный opt-in AI.
- Сервер хранит момент включения зеркалирования и меняет его только при переходе false → true. Gate читает свежую Integration под блокировкой до записи сообщения. Входящий `event.occurred_at` — время провайдера. `event.observed_at` — момент первой записи в durable raw adapter DB, неизменный при ретраях. Оба времени должны доказывать принадлежность к периоду включения. Документируем допуск ±30 с относительно Chatballs и консервативную границу `enabled_at + 30 с`. События в окне неопределённости, за границей, без `observed_at` или при выключенном зеркалировании получают штатный 202 без побочных эффектов. Старые v1 envelopes продолжают проходить проверку формы. Адаптер не заменяет provider timestamp текущим временем.
- `message.observed_outgoing` допускает optional `message.reply_to_external_message_id` для текста. Сохраняем provider timestamp и reply ID. Независимые ответы не формируют исходящую команду и не меняют право AI на будущий ход или назначение оператора. Unknown получает retryable 409, конфликт идентификаторов и неоднозначность не создают запись.
- AI opt-in использует текущую автономную политику организации и канала. Текстовую команду формируем с существующей стабильной command identity. Claim до первого HTTP сериализуется с mirror по Conversation, как у Gateway. После claim запрос может уже выйти за пределы Chatballs. Повтор использует прежний command ID, а не новую отправку. Echo и receipts применяются и к AI.
- TG/MAX сохраняют reconciliation, lease/fencing и raw table. Результат точной корреляции идёт штатным путём delivery receipts. Обнаруженный внешний текст обоих адаптеров проходит общий projection/HTTP. Для непредставимой формы события сохраняется терминальная причина, без усечения медиа до текста.

## Работы и проверки

- [x] Chatballs config/UI. В `integrations/services.py`, `management.py`, `serializers.py` нормализовать и сериализовать поле, сохранить секреты, callback, командный URL и media flags, записать изменение в существующий audit. Выделить нормализацию Connector в отдельный модуль. Подготовить tests для дефолта, валидации, прав и PATCH. В `features/integrations/IntegrationForm.tsx` использовать штатный SwitchButton и ключи RU/EN. Проверить связанный Vitest и TypeScript.
- [x] Chatballs mirror. В `api_connector/observed.py` проверить временную границу на заблокированной Integration. В `conversations/external_outgoing.py` записать внешний timestamp и reply ID, сделать дедуп по маршруту и вызывать общую ревизию под блокировкой диалога. Тесты: toggle/очередь/re-enable, дубли и конфликт ID, unknown и tenant, поздний replay после нового хода и гонки PostgreSQL.
- [x] Chatballs AI. В ingress/routing убрать operator-only guard только у явно включённого AI Connector с доступным transport. Использовать устойчивые Connector command и Native Mirror publication, отбрасывать супрессированные ответы из истории и расширить допустимых авторов echo/receipt. Тесты: обычный Connector остаётся operator-only, включённая текстовая AI-команда идемпотентна, до-claim supersession и гонка с claim.
- [x] Green Adapter. Подключить общий outbound observation в single/multi-instance webhook и worker TG/MAX. Использовать первую запись raw в первоначальной отправке и retry, поддержать quote ID и явно диагностировать неподдерживаемый медиа-тип. Тесты: own echo, ambiguous, unsupported media, старый raw при retry, lease, два экземпляра TG/MAX.
- [x] Контракт, совместная проверка и legacy. Изменить OpenAPI, JSON Schema, conformance, руководство и настройку. В изолированном PostgreSQL запустить оба runtime и реальный Connector HTTP с синтетическим провайдером. Проверить TG/MAX, toggle, повтор, собственную отправку, отсутствие Legacy HTTP. Сохранить VK, Connector ingress/outbound/media. Убрать Gateway из создания новых подключений после проверки, без переноса production.
- Публикация через два связанных Draft PR. [Green Adapter #29](https://github.com/amonrapmon/chatballs-green-adapter/pull/29).

## Зависимости оставшегося Gateway

Кандидаты после миграции установок: `gateway_ingress/`, подключение URL в `chatballs_backend/urls_app.py`, `conversations/gateway_delivery.py`, `gateway_http.py`, `gateway_event_handlers.py`, Gateway-проверка Integration и старые настройки формы. Транспорт Caddy и доменные route для порталов используются отдельно.

Общие компоненты: `native_mirror/supersession.py`, `NativeMirrorConversationState`, фильтрация скрытых публикаций, контракты и реализация VK. `NativeMirrorReceipt` и replay требуют отдельной проверки живых Gateway pending receipt и остаются нужны там, где их использует VK. Publication-таблицу и транзакционные проверки нужно сохранить для защищённой отправки AI.

Исторические Django migrations, RLS guards и сохранённые `GATEWAY`-строки остаются совместимыми. Перед прекращением поддержки нужен утверждённый перенос или документированный период совместимости. Существующие очереди, внешние ID, канал, связь разговора с подключением, команды и их статусы требуют доказательства сохранности. Смена provider у строки Integration сама по себе этих гарантий не даёт.


## Как повторить парную проверку

В Green Adapter собрать `npm run build:tg` и `npm run build:max`. В среде
тестов Chatballs задать `CHATBALLS_TEST_GREEN_ADAPTER_ROOT` на этот checkout
и `CHATBALLS_TEST_GREEN_ADAPTER_DB` на выделенную локальную PostgreSQL БД с
именем `test_*`. Тест сам применяет миграции адаптера. База приложения должна
быть отдельной от adapter DB.

Из `apps/backend` выполнить
`python -m pytest -q --reuse-db chatballs/api_connector/test_green_native_mirroring.py`.
Тест запускает Chatballs HTTP, по два источника TG и MAX с реальными webhook,
delivery и status worker и синтетическим HTTP-провайдером на loopback. Источники
повторяют одинаковые provider/chat ID, чтобы проверить изоляцию в общих
таблицах. Сценарий проверяет обратный вызов, сохранение цитаты, отсечение
старого наблюдения, повтор, штатную отправку сотрудника и её отклик.

## Условия миграции старых установок

Перед отдельным решением о выводе Gateway потребуется инвентаризация
активных подключений, незавершённых команд и Native Mirror receipts по
организации и источнику. На копии базы нужно доказать сохранность истории,
токенов, маршрутов, связей диалогов с каналами и идентичностей провайдера,
проверить доставку накопившихся событий и возврат на прежний транспорт.
Переход runtime возможен после согласования владельцем способа переноса и
процедуры переключения. Исходные данные и схема миграций в задаче сохраняются.


## Результат парной проверки

Финальный прогон на текущих сборках завершился успешно для двух TG и двух MAX.
Общий Adapter PostgreSQL использовался разными source ID с одинаковыми
идентификаторами чатов и сообщений. Webhook, зеркалирование и проекция
статусов прошли через реальные HTTP-точки процессов. Для каждого внешнего
события проверялся конечный статус raw-строки, включая ACK при выключении.

Отдельные тесты PostgreSQL покрывают блокировку настройки перед записью,
конкуренцию одинаковых событий, привязку доставки AI к ревизии и его opt-in,
а также проверку под runtime-ролью с RLS. Прошли проверки VK, Connector media
lifecycle, схемы v1 и тесты формы. Живой GREEN-API и переключение старой
установки в этот прогон не входят.
