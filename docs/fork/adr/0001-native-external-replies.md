---
id: "FORK-ADR-0001"
title: "Внешние исходящие реплики: наблюдение отдельно от управления диалогом"
status: proposed
date: 2026-10-08
base: "amonrapmon/chatballs@330960b81ac78dc36e1b05fbfa2730b7888bb3bc (upstream v1.17.2 + Gateway)"
research_updated: 2026-10-09
---

# FORK-ADR-0001. Native External Reply Extension

## 1. Контекст и граница решения

Chatballs нативно обслуживает VK; TG/MAX поступают через `intercom-gw` и Gateway ingress. Необходимо показывать в истории внешние исходящие реплики, которые операторы отправляют из нативных приложений, без обязательной передачи управления человеку. Цель форка — иметь минимальные, проверяемые изменения в upstream-файлах и уметь отключить расширение без отката релизов.

**Этот ADR — проект решения, а не разрешение на реализацию.** Он дополняет, но не отменяет upstream `.skaro/adr/0002-ai-first-obrabotka-i-ruchnoy-perehvat.md`: явный takeover по-прежнему переводит в `HUMAN`, а автоматического возврата к AI из `HUMAN` нет. Обозначим внешнюю реплику как `OBSERVE`; явный перехват — `TAKEOVER`. Это разные команды.

### Факты, подтверждённые кодом ветки

- `gateway_ingress/operator_mirror.py`: событие TG/MAX проходит Gateway-auth и сверку `source_id`, дедуплицируется через `InboxEvent`, ищет единственный открытый `Conversation`, записывает `Message(OPERATOR)`, **затем ставит `control_mode=HUMAN`**. Текущая проверка membership привязана к `native_operator_user_id`. Это поведение надо сохранить в LEGACY, но не в новой семантике.
- Там же уникальность события отмечается **до проверки наличия диалога**; при 0/2 найденных диалогах событие логируется и фактически считается обработанным. Для нового слоя нужна явная политика `retry / dead-letter / permanently skipped`, чтобы не терять сообщения без следа.
- `conversations/transports/vk.py`: `_normalize` принимает только `message_new` и отбрасывает `from_id < 0`. `message_reply` не входит в нынешний поток входящих. Нельзя получать исходящие просто снятием фильтра `from_id`.
- `conversations/transports/vk_send.py`: `messages.send` формирует случайный `random_id`; `_send` возвращает только `bool` и не хранит provider message ID. Самоэхо после отправки Chatballs пока нельзя надёжно исключить по хранимой корреляции.
- `conversations/poller.py`: ошибки `ingest_inbound` ловятся и логируются по сообщениям, после чего `poll_marker` может быть продвинут. Для обязательных внешних событий это недопустимый безусловный ACK.
- `conversations/ai_turn.py`: `PENDING`/`RUNNING` на входящем `Message`; `_begin` проверяет режим, но после генерации `record_turn`, `store_answer` / `store_failure` сохраняют результат в транзакции, а `_deliver` отправляет **позже, вне транзакции**. Есть гонка между проверкой актуальности, записью и отправкой.
- `conversations/models.py`: `AiTurnState` содержит `NONE/PENDING/RUNNING/DONE/FAILED`. Отдельного `SUPERSEDED` нет; `Message.external_id` сам по себе не уникален.
- `.skaro/adr/0028-...`: `worker-events` независим от poller, а выполнение хода может быть долгим и возобновляемым.

### Исторический VK mirror: проверенное решение до Chatballs

Проверена историческая реализация `intercom-gw@b3fdf9f` (до удаления Chatwoot legacy).
Старый `vk-gateway` принимал **VK Callback API**, нормализовал `message_new` как
incoming, а `message_reply` как outgoing с `peer_id`, `id`,
`conversation_message_id`.

- `vk-gateway/src/services/native-reply-mirror-service.ts` искал outbound
  `message_mappings` по `(service, externalChatId, externalMessageId, sourceId)`.
  При найденном mapping пропускал повтор, иначе записывал outgoing в Chatwoot
  от служебного `nativeBridgeUserId`, затем создавал mapping.
- `vk-gateway/src/services/outbound-dispatch-service.ts` сохранял VK `messageId`
  из успешного `messages.send` в delivery record и outbound mapping; в БД
  действовал составной unique index для provider message mapping.
- Это подтверждает **реально реализованную схему зеркалирования с дедупликацией**,
  но не исключает гонку `callback-before-mapping`, не доказывает строгое
  exactly-once и не устанавливает личность конкретного администратора.
- Удаление Chatwoot legacy коммитом `intercom-gw@f76f218` означает, что этот
  код теперь только источник инженерного опыта, не активный VK runtime.

**Ключевое различие:** прежний gateway использовал VK **Callback API**,
нынешний встроенный Chatballs VK использует **Bots Long Poll**. Не переносить
parser/receiver буквально; проверить поля и подписки на реальных обезличенных
событиях нового транспорта.

### Результат исследования WEB и штатных TG/MAX

- `IntegrationProvider.WEB` есть браузерный виджет, **не** универсальный внешний
  gateway. `webchat/services.py` создаёт `InboundMessage` с новым UUID и
  вызывает общий `ingest_inbound()`, `webchat/sessions.py` обслуживает сессии,
  `webchat/message_history.py` отдаёт историю виджету через GET.
- В `conversations/transports/__init__.py` для WEB зарегистрирован `_web_noop`:
  сообщение уже сохранено в БД, и браузер получает его polling. Нет встроенной
  доставки обратно в Green-API Telegram/MAX, провайдерных message IDs или
  статусов внешней отправки.
- Штатные `telegram.py` и `max.py` имеют полноценные Bot API poll/send/media
  адаптеры. Наш `intercom-gw` отличается наличием durable delivery commands,
  attempts, provider-event reconciliation, status projections и source-scoped
  worker claim. Эмуляция WEB-сессий была бы регрессией, не упрощением.
- `gateway_ingress/services.py` и WEB уже используют **один** `ingest_inbound()`.
  Общий AI/conversation core дублировать не требуется.

**Решение:** TG/MAX оставляем на действующем `intercom-gw`; WEB оставляем
браузерным; VK остаётся во встроенном Bots Long Poll. Унифицируем через
`native_mirror` только обработку **внешних исходящих**, сохраняя тонкие hooks и
upstream-совместимое поведение при выключении расширения.

### Внешнее подтверждение / ещё проверить

- Для VK Bots Long Poll нужны обезличенные реальные `message_reply` и `messages.send` responses. Проверить `id`, `peer_id`, `conversation_message_id`, `from_id`, `out`, возможные `random_id` и `admin_author_id`. Наличие `admin_author_id` не гарантировано, само по себе не подтверждает членство в Chatballs; отсутствие поля не доказывает происхождение от бота. Не предполагать эквивалентность payload старому VK Callback API.

## 2. Решение: границы ответственности

```text
TG / MAX native app            VK Bots Long Poll
       |                               |
   intercom-gw                    VK adapter
       |                               |
POST /operator-mirror/                 |
       +---------------+---------------+
                       |
             native_mirror.accept(...)
                       |
      classify -> dedup -> tenant match -> persist
                       |
         (if authoritative) AI supersession
                       |
           Chatballs canonical history
```

`intercom-gw` остаётся транспортом и не принимает решений о `control_mode`, состоянии AI-turn или видимости сообщения. Chatballs владеет canonical history, дедупликацией, правами, классификацией и отменой устаревшего ответа. Для VK не вводить второй поллер с отдельным cursor для того же сообщества и не маршрутизировать его через intercom-gw.

Новый код — отдельный пакет `apps/backend/chatballs/native_mirror/` (название предварительно): `contracts`, `classification`, `service`, `supersession`, `vk_adapter`, `policy`, `audit`. Модель и миграции, если нужны, **добавочные**, с tenant RLS и ограничениями, принятыми в Chatballs. Нельзя дублировать upstream-функции или monkey-patch их.

## 3. Семантические инварианты

1. **OBSERVE не равен TAKEOVER.** Внешняя реплика не меняет `control_mode` (AI/HUMAN/PAUSED) и не назначает сотрудника. Существующие upstream-команды takeover, handoff и PAUSED не переписываются.
2. Если `control_mode=AI`, *доверенная авторитетная* внешняя реплика может сделать ранее начатый AI-turn устаревшим. Следующее входящее сообщение клиента создаёт обычный новый ход.
3. Если `control_mode=HUMAN/PAUSED`, состояние сохраняется; зеркальная реплика не возобновляет AI и не отменяет явный takeover.
4. События от одного канала разных организаций никогда не смешиваются; источник, организация, подключение и открытый диалог проверяются до записи.
5. Дедупликация должна опираться на **провайдерный event/message ID, scoped by integration**, а не текст или время. Для echo использовать отдельную корреляцию исходящих Chatballs. В отсутствие достоверных ID запрещено считать строковое совпадение доказательством echo.
6. Сообщение Chatballs, пришедшее обратно от VK, **не создаёт второго Message** и не подавляет собственный AI-turn.
7. Внешнее сообщение без подтверждённой роли / происхождения не объявляется репликой человека. Для неизвестного автора применять явную policy: `unclassified`, а не слепой `OPERATOR + supersede`.
8. Ошибка временного сохранения не приводит к ACK upstream события. Отсутствие или неоднозначность диалога — отдельный зафиксированный outcome, не «успех без сообщения».
9. Feature policy допускает отключение без изменения схемы и без удаления исторических данных; отключение не ломает остальной транспорт.

## 4. Модель событий и классификация

Предлагаемое DTO `ExternalReplyEvent`: `provider`, `integration_id`, `source_id`, `external_chat_id`, `event_id`, `external_message_id`, `external_reply_to_id`, `occurred_at`, `text`, `origin_kind`, `origin_identity`, `origin_confidence`, `vk_admin_author_id` (optional, если проверен), `raw_event_ref` (не хранить токены). Клиентские сообщения НЕ отправлять через этот интерфейс.

Классы событий:

- `SELF_ECHO`: сообщение от собственного отправляющего контура Chatballs, подтверждённое correlation ID/provider message ID; только ack/telemetry.
- `EXTERNAL_AUTHORIZED`: подтверждённая внешняя отправка из доверенного источника; отображение и supersede разрешены политикой подключения.
- `EXTERNAL_UNCLASSIFIED`: отправка от имени сообщества без надёжной атрибуции; не утверждать, что это человек. Обработка зависит от явно согласованной policy; по умолчанию без supersede.
- `INVALID/UNSUPPORTED`: отсутствие обязательных полей, неверный чат, проблемы безопасности; отказ с ясной причиной.

`author_user` заполнять только для подтверждённого члена нужной организации. Для VK, если личность отправителя не доступна, использовать согласованное служебное представление «Внешний VK» вместо выдуманного пользователя; детали UX и author_type согласовать отдельно. Расширение v1 — только **личные текстовые** сообщения; вложения, редактирование, пересылки и групповые чаты вне объёма.

Историческое зеркало Chatwoot использовало служебного `nativeBridgeUserId`, а не удостоверенную личность VK-администратора. Даже подтверждённый `admin_author_id` можно отобразить как сотрудника только после явного tenant-aware mapping к `OrganizationMembership`.

## 5. Надёжность и транзакции

### Приём и ACK

Нужен durable staging/инбокс со статусами обработки и уникальными ключами. Маркер VK можно продвигать только после долговременного сохранения интересующих событий (или успешной атомарной обработки в рамках согласованной транзакции). Временная ошибка -> retry; постоянно неподдерживаемое/неоднозначное событие -> явный recorded outcome/dead-letter. Не считать предупреждение в логах заменой durable записи.

Для Gateway v1 сохраняем HTTP schema и auth. Перевод обработки в отдельный сервис не должен менять SLA/idempotency endpoint. Переход на staging, если нужен, оформляется совместимо, с явной семантикой ответа, а не молчаливым изменением 202/409.

Для VK echo переиспользовать концепцию `messages.send -> provider messageId -> outbound mapping` из старого gateway, но покрыть callback-before-mapping, provider response lost, redelivery и restart. Не переносить Chatwoot API, его таблицы или Callback consumer в Chatballs.

### Supersession AI

**Отклонено:** одна проверка `should_publish()` перед `_deliver()`. AI уже мог сохранить текст, вызвать handoff/fallback и создать tool-call side effects.

Выбираем направлением исследования **отдельное per-conversation revision/epoch состояние** и durable event для аудита без существенной переделки `Conversation`. При зеркальной авторитетной реплике ревизия увеличивается, а начатые ранее PENDING/RUNNING ходы помечаются stale/terminal согласованным способом. Для RUNNING guard должен сравнивать актуальную ревизию с захваченной на старте. Для PENDING нельзя «захватить свежую ревизию» уже после события и случайно разрешить старый ход: либо сохраняется snapshot при постановке в очередь, либо атомарно маркируются все старые запросы.

Все пути записи должны учитывать stale: `store_answer`, `store_failure`, voice/transcription path, handoff, system events, notifications, `record_turn` и tool-call events. **Уже выполненные внешние HTTP/MCP tool side effects неотменяемы**: потенциально побочные инструменты нуждаются в отдельной политике, а не в обещании rollback модели.

Использовать фиксированный порядок блокировок, например Conversation -> mirror state -> inbound Message, во всех конкурирующих ветках. Атомарность внутри одной транзакции обязательна. Избегать чтения устаревшего `Turn.conversation` как основания для commit.

После записи AI-ответа есть отдельное **окно публикации**. Гарантию сформулировать до кода:

- До durable publication claim supersede может подавить ответ.
- После начала внешней отправки отмена доставки не гарантируется; **exactly-once across network не обещать**.
- Для сильной гарантии потребуется связать публикацию с outbox и состоянием `claim/send`, без удержания DB-lock на время сетевого запроса. Только pre-send check без claim это TOCTOU.
- Внутренний web-chat уже читает Message из БД; stale-ответ нельзя сохранять как видимое сообщение в ожидании последующей отмены.

Выбор между расширением существующего delivery outbox и отдельной попыткой публикации — решение этапа 0.5 после анализа контрактов, до реализации этапа 2.

## 6. Feature policy и обратимость

Политика per installation/per integration (точный механизм после проверки существующих настроек):

| Значение | Поведение |
| --- | --- |
| `DISABLED` | Не зеркалировать внешние исходящие; остальной транспорт/AI работает как обычно |
| `LEGACY` | TG/MAX существующий mirror с takeover в HUMAN; VK исходящие игнорирует |
| `SHADOW` | Сохранить legacy-поведение TG/MAX; новую классификацию только считать и логировать без нового эффекта, VK не создавать зеркальные Message |
| `ENABLED` | Использовать unified native mirror + согласованный supersede |

**По умолчанию LEGACY**, чтобы обновление форка не меняло действующие диалоги. `ENABLED` включать по подключениям после тестов. Не заполнять непроверенные параметры внешнего события из предположений. Логи маскировать, не хранить API key, токены и текст сообщений без необходимости.

Переход `ENABLED -> LEGACY/DISABLED` меняет только будущие события. Уже записанные Message и завершённые ходы не удаляются. Данные миграций остаются, reverse migration в качестве «выключателя» не используется.

## 7. Бюджет форка и upstream compatibility

- Новые файлы в `native_mirror/*`, его tests и docs — основной объём работы.
- Изменения upstream-модулей только в виде тонких интеграционных точек. Кандидаты: `transports/vk.py`, `conversations/poller.py`, `conversations/ai_turn.py` и точки публикации ответа. Не обещать две строчки до проверки гарантий.
- Для уже кастомного `gateway_ingress/operator_mirror.py` менять только делегирование; `intercom-gw` не меняется без контрактной причины.
- Фиксировать каждому core hook контракт, вход/выход, тест-инвариант, fallback при `DISABLED` и заметку для следующих upstream merge.
- Для каждой новой версии сравнивать именно указанные точки, даже если git merge проходит без конфликтов.

- Для каждого core hook вести **fork compatibility checklist**:
  `path/symbol | цель патча | режимы и fallback | upstream-поведение при отключении | targeted tests | риск merge | проверенная версия`.
- При `DISABLED` встроенный VK продолжает принимать `message_new`, отправлять
  сообщения и работать с AI точно как штатный upstream; WEB не меняется.
  Для TG/MAX default `LEGACY` должен сохранить нынешнее зеркало и HUMAN takeover.
- Не добавлять второй VK poller/cursor, копию `ingest_inbound`, эмуляцию WEB,
  monkey-patch или самостоятельный AI pipeline. Чистый git merge сам по себе
  не означает прохождение upgrade compatibility gate.

## 8. Не принятые решения / условия допуска к реализации

1. Какие поля (включая потенциальный `admin_author_id`) реально приходят в Bots Long Poll `message_reply`, как они отличаются от Callback API и при каких условиях разрешена атрибуция к члену организации? Нужны masked payloads и явная policy.
2. Как Chatballs коррелирует **все** собственные отправки VK, включая AI, ручной ответ, приглашения и файлы, если echo пришёл раньше записи response ID?
3. Как сделать durable ACK на существующем poller без регрессий входящих и увеличения core-diff?
4. Какую гарантию supersede/отправки можно предоставить при in-flight network-send? Нужны конкурентные тесты.
5. Где и как хранить state/revision в отдельной tenant-aware модели, с RLS и миграцией.
6. Как отображать VK native reply при неизвестном личном авторе, не выдавая его за конкретного сотрудника.
7. Как учитывается уже исполненный инструмент AI, если после него пришла авторитетная внешняя реплика?

**Решение:** принять этот ADR как направление; детали выше закрыть прототипом и тестами ДО runtime-включения. Ни одного изменения upstream lifecycle до отдельного согласования.

### Проверенные репозитории и исходники, 2026-10-09

- VK Callback normalizer: https://github.com/amonrapmon/intercom-gw/blob/b3fdf9f90be9269edda8dec50d37604d4e857c37/vk-gateway/src/transports/vk/vk-normalizer.ts
- Историческое VK зеркало: https://github.com/amonrapmon/intercom-gw/blob/b3fdf9f90be9269edda8dec50d37604d4e857c37/vk-gateway/src/services/native-reply-mirror-service.ts
- Исторический VK outbound mapping: https://github.com/amonrapmon/intercom-gw/blob/b3fdf9f90be9269edda8dec50d37604d4e857c37/vk-gateway/src/services/outbound-dispatch-service.ts
- Удаление Chatwoot legacy: https://github.com/amonrapmon/intercom-gw/commit/f76f218bd306826ae37f21617f5d32691aa6e6f5
- Текущий Chatballs `@330960b`: `webchat/{services,sessions,message_history}.py`, `conversations/transports/{__init__,telegram,max,vk,vk_send}.py`, `gateway_ingress/services.py`.
- Текущий `intercom-gw@main`: `db/src/schema.ts`, `tg-gateway/src/services/delivery-command-worker.ts`, `tg-gateway/src/services/green-api-delivery-event-service.ts`.

### References (public VK format, not a substitute for real event samples)

- VK API message schema: https://github.com/VKCOM/vk-api-schema/blob/master/messages/objects.json
- Bots Long Poll event types (`message_reply` exists): https://vk-api.readthedocs.io/en/latest/bot_longpoll.html
- Chatballs fork baseline: https://github.com/amonrapmon/chatballs/tree/c8af373be48e3c7633a3f23d9799f720255de14d
