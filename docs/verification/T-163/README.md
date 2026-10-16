# T-163: сохранённые оформленные ответы

Проверка выполнена в окружении `skaro-chatballs-t-163` на исходниках задачи.
Frontend `http://localhost:20004` и widget `http://localhost:20005` используют
`VITE_DEV_API_TARGET=http://backend-app:8000`; readiness на backend задачи
`:20002` подтвердил database/redis. Документированный backend-admin добавлен
через configure_environment; init выполняет штатные миграции.

После обнаруженного зависания Vite proxy добавлен предусмотренный
compose.dev.yaml nginx gateway (Skaro выделил `GATEWAY_HTTP_PORT=20012`).
Финальные browser-проверки выполнены через `http://localhost:20012`:
`/api/` идёт непосредственно в backend-app:8000, UI — в тот же frontend.
Readiness через gateway вернула database=true/redis=true. Ответы не
перехватывались и не подменялись. В запуск окружения добавлен перезапуск
frontend после compose, чтобы не оставлять зависшие proxy-соединения при
обновлении backend; это настройка только окружения задачи через Skaro.
Повторный start_environment после этого завершился `running and ready`;
первоначальный readiness-тайм-аут устранён. Gateway подтверждён через compose ps.

Уже установленный DemoDataset организации 1 и существующий ADMIN проверены
read-only. Вход выполнен данными из organization.json. Seed и изменения
учётных данных не выполнялись. Полный набор тестов не запускался.

## Контрольные сообщения и границы проверки

В исходной копии не было Skill и сообщений формата 1; был только DEMO без
поддержки подготовки структурированного ответа и не было внешних инструментов.
Владелец отдельно разрешил контрольные сообщения только в БД задачи,
собранные штатным серверным compiler, без подмены backend/API.

`control_messages.py` исполнен один раз через manage.py shell в backend-admin
с проверкой COMPOSE_PROJECT_NAME и отдельным task-only opt-in. Он использовал
order_basis/render_template и сохранил снимки в обычные Message. Созданы
отдельные WEB-подключение/виджет и контрольный контакт в disposable БД.
Публичная сессия открыта обычным действием виджета; контрольный диалог привязан
к её контакту. Реальные внешние сообщения не отправлялись. Последующая
Telegram-контрольная реплика также сохранена только в БД, без отправки.

Это проверка чтения/отображения снимков, не E2E внешнего AI или системы
заказов. Общий runtime, подготовка в проверочном чате и защита от поздней
фиксации проверены в изолированной тестовой БД существующими целевыми тестами.

## Исполняемые проверки

Команды из корня worktree, после start_environment:

```powershell
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run build
docker compose exec -T web-chat npm run build
docker compose exec -T frontend npm --workspace @chatballs/ui run typecheck
docker compose exec -T frontend npm --workspace @chatballs/ui test -- src/messages/PreparedMessage.test.tsx src/messages/snapshot.test.ts
docker compose exec -T frontend npm --workspace @chatballs/internal-ui test -- src/features/conversations/SnapshotMessage.test.tsx src/features/agents/test-chat/TestChatFeed.test.tsx src/features/agents/test-chat/model.test.ts src/features/conversations/feed.test.ts src/features/conversations/historyScrollState.test.ts src/features/conversations/useConversationEvents.test.tsx
docker compose exec -T web-chat npm test -- src/snapshots.test.tsx src/widgetAppearance.test.tsx
docker compose exec -T backend-admin pytest -q --reuse-db --tb=short chatballs/conversations/test_template_updates.py chatballs/ai/test_template_completion.py chatballs/ai/test_template_realtime.py chatballs/conversations/test_history_window.py chatballs/conversations/test_voice_messages.py chatballs/conversations/test_attachments.py chatballs/conversations/test_email_media.py chatballs/conversations/test_email_ui_contract.py
docker compose exec -T backend-admin ruff check chatballs/conversations/template_updates.py chatballs/conversations/message_views.py chatballs/conversations/test_template_updates.py chatballs/conversations/test_voice_messages.py chatballs/conversations/test_attachments.py chatballs/conversations/test_email_media.py chatballs/conversations/voice_testing.py
git diff --check
```

Результат: обе сборки, UI typecheck и Ruff прошли; 14 renderer, 34 internal UI,
8 widget и 51 backend тест прошли. Логи сохранены рядом. Vite предупреждает
о крупных chunks. Первый регрессионный прогон выявил устаревшие точки patch
в старых медиа-тестах после прежнего выделения SMTP/upload policy; исправлены
пути и завершение SMTP double. Подготовка голосовых и тест почтового вложения
вынесены в небольшие модули, повторный прогон зелёный.

## Зафиксированные результаты браузера

Task-local Playwright; реальный backend, без route.fulfill и fake backend.
Baseline прочитан из исходного HTML и его support.js/chat-model.js в отдельную
страницу браузера, сохранены baseline-light/dark. Это просмотр baseline,
не подмена приложения.

| Проверка | Наблюдение | Кадры |
|---|---|---|
| W1/W2 | Короткий заказ и длинный из 7 позиций читаются в пузыре; в длинном итог 93 100 ₽, названия переносятся, суммы справа. | w1-short-with-eta, f1-long-light, w4-360-light, widget-* |
| W3 | Реальный сохранённый статус без eta не содержит строки ожидаемого времени, тире или пустого места; со сроком строка есть. | feed-light |
| W4 | Окно 360: document/body scrollWidth=360, карточка 271/271; окно 440: 440/440, карточка 322/322. В обеих media-темах 7 строк и тот же итог. | widget-360/440-light/dark |
| F1 | Автор AI, время, check и название отправленного шаблона сохранены. Раскрытый текст посимвольно совпал с Message.text из штатного API; кнопка меняет подпись и закрывает текст. | f1-text-expanded-light |
| F2 | Сохранённое text-представление показало текст заказа без iframe и действия карточки. | feed-light |
| F3, правка | Штатный PUT revision 1→2 переименовал шаблоны. SHA-256 снимка text/contentHtml/presentation/template/representation до и после одинаков: a81031058414ae45fc345db6e3dfcf37906f61f5af18782a6a0b82fe6bff1079. После перезагрузки осталось старое имя «Карточка заказа», появилось пояснение с датой. | f3-revised-light |
| Точные ширины | В реальной ленте временно ограничена ширина пузыря до 300/340; диагностическое ограничение снято после измерения. В обеих темах внутренние размеры 284/284 и 324/324 (clientWidth/scrollWidth), 7 строк, итог 93 100 ₽. | card-300/340-light/dark |
| F3, удаление | Контрольный навык удалён штатным DELETE; после перезагрузки SHA-256 снимка остался тем же, имя прежнее, templateUpdatedAt отсутствует и пояснения нет. | f3-deleted-light/dark |
| F2, канал | В отдельном контрольном Telegram-диалоге текст показан без iframe и без действия текстовой версии; контрольная реплика не отправлялась наружу. | f2-telegram-light/dark |
| История | Прокрутка вверх загрузила 50→60 сообщений: 60 уникальных id, порядок сохранён, после следующего опроса всё ещё 60. Якорь message-156 до/после на 96 px; scrollTop 20→1420, смещение якоря 0 px. | Результат измерения Playwright |
| Изоляция | Все 46 видимых iframe загруженного окна имеют sandbox="" и no-referrer. Соседние сообщения и оболочка сохранили стили. | feed-dark, f3-revised-dark |
| Общий снимок | srcDoc длинной карточки в виджете и сотруднику посимвольно одинаков; видимые документы opaque (contentDocument=null), в измерительных документах 0 script. Публичный UI не сделал запросов skills/templates. После последнего удаления в ленте 0 пояснений. | Финальное измерение Playwright |
| RU/EN | EN «Text version» раскрывает сохранённый RU-текст без его изменения; «Hide text version» закрывает. Обе локали проверены также компонентным тестом, EN key parity — сборкой. | f1-text-en-light |
| TestChatFeed | Штатный DEMO вернул ответ о сроках, затем передачу человеку. Существующая оболочка, ноль tool-call-chip, маркер передачи не показан. Обычный ответ снят в обеих темах. | test-chat-en-light/dark |
| Старые сообщения | Входящая HTML-почта остаётся sales-email-body-frame (1), prepared-message-frame (0); голосовое сохраняет кнопки воспроизведения и расшифровку. Вложений в копии нет, их непосредственно затронутые регрессии прошли в test_attachments/test_email_media. | legacy-mail-dark, legacy-voice-dark |
| Повреждённое | Неподдерживаемая presentation показала сохранённый текст статуса без iframe/сырого HTML. | feed-light |

Оформленный ответ в проверочном чате проверен связкой: TestChatFeed SSR
использует тот же PreparedMessage и серверный snapshot; runtime-тест проверяет
настоящий endpoint с выбором снимка в изолированной тестовой БД. Получение
оформленного ответа от DEMO в живом браузере не заявляется: DEMO не умеет
передавать структурированные аргументы подготовки. Подмена test-chat API не
использовалась. Это ограничение провайдера, не отдельная реализация renderer.

Профиль проверяющего возвращён к RU/light. В продуктовом UI не добавлены
новые экраны, сообщения внутренних операций или состояния вне соглашения.
После визуальной сверки сделана только локальная CSS-правка: пояснение F3
явно выровнено влево, как в baseline, без наследования выравнивания автора.
Повторная npm-сборка для этой CSS-правки не запускалась по правилу владельца.
Штатное окружение перезапущено через Skaro; computed textAlign="left"
проверен в обеих темах, кадры f3-revised обновлены. Для финального кадра
контрольная конфигурация временно восстановлена в БД задачи с тем же UUID,
затем снова удалена штатным DELETE; сохранённые сообщения не пересобирались.

## SRP / NO GOD FILES

`structure.txt` фиксирует размеры. Все новые компоненты меньше 180 строк;
функциональные модули и изменённые тестовые файлы меньше 300 строк.
Крупные существующие ru/en агрегаторы получили только import/spread малого
каталога snapshots. Подготовленный документ/безопасный fallback и учёт
прокрутки разделены в packages/ui; metadata/text disclosure — малый компонент
ленты; MessageBubble по-прежнему владеет только оболочкой. Дата новой ревизии
добавляется отдельным серверным модулем за один запрос на окно.

Единственный renderer сохранённого HTML — общий PreparedMessage. Новый
dangerouslySetInnerHTML не вводится; почтовый renderer не менялся. Показанные
карточки используют штатные редактируемые исходники основы, не захардкожены
в React. Дополнения текстовой версии/TestChat/F3 соответствуют
docs/agent-skills-ui-agreement.md.
