# Проверка интеграции T-076

Проверено 13.10.2026 в штатном окружении `skaro-chatballs-t-076`.
Worktree и ветка задачи сохранены. В первое слияние включена main c7558f9d:
T-122 ced58038, T-128 dd4978e1 и T-136 c7558f9d.

Сохранены участники, передачи, внутренние комментарии, AI-помощь, шаблоны,
отчёты поддержки, клиентские оценки и анализ качества из main. Почтовый
редактор включён в общий переключатель аудитории; почтовый текст и вложение
хранятся отдельно от ответа/комментария. Права почтового ответа используют
общий сервис main, события и уведомления входящего письма также сохранены.
Исторические поля письма, вложения, журнал, повторы и времена наблюдений
T-076 сохранены. Merge-миграции не содержат операций с данными.

## Выполненные проверки

- Образ backend собран штатным `start_environment` с `--build --wait`.
- Сборки internal-ui и web-chat прошли; у internal-ui осталось предупреждение
  Vite о размере chunks. Ошибки JSX и отсутствующий ключ Email, выявленные
  промежуточными сборками, исправлены; финальная сборка успешна.
- Django check: ошибок нет; makemigrations --check --dry-run: изменений нет.
- Серверный адресный прогон: 52 passed (81.44 s), затем 1 passed (21.21 s)
  для проверки Email на странице контакта, перенесённой из большого общего
  файла в test_email_ui_contract.py. Успешные наборы повторно не запускались.
- internal-ui: 25 passed в 6 адресных файлах. Проверен собственный API письма
  при наличии AI-черновика и вложения ответа; незаполненные переменные
  блокируют письмо, ответ и комментарий.
- web-chat: 3 passed (сигналы и авторство участников); loader: 6 passed.
- Ruff по объединённым серверным модулям: ошибок нет. git diff main --check прошёл.
- Проверены размеры и ответственность изменённых файлов: Composer 119 строк,
  модель редактора менее 180 строк, почтовый черновик вынесен в отдельный hook.
  Общий test_chat_extras.py относительно main не расширен.
- Readiness через frontend и backend: database=true, redis=true. Vite proxy
  указывает на backend-app этого окружения.

## Браузер

Playwright, реальный backend: http://localhost:20176,
http://localhost:20174 и http://localhost:20177. Использован уже установленный
демо-администратор; seed и изменение учётных данных не выполнялись.

Сверены `design/baseline/platform-expansion/Чат · состояния.dc.html`
(E1–E7, V1) и `Чат · совмещённые кадры.dc.html` (K1, M1–M2).
Ранее согласованные владельцем изменения сохранены: поле Email в карточке
контакта и полная карточка письма на телефоне.

На обращении №36 проверены три вкладки, адрес, ящик, тема, почтовый черновик,
переключение в комментарий и обратно. Комментарий сохранён штатным API (201),
почтовый текст и тема сохранены отдельно, AI-кнопка в письме отсутствует.
Журнал показывает реальные прошлые ошибки SMTP, инициатора повторов и
предупреждение: SMTP-принятие не подтверждает доставку/прочтение.
Проверено отсутствие горизонтальной прокрутки на 390×844; поля, аудитория
и редактор занимают отдельные строки. Скриншоты приложены рядом с отчётом.
В копии окружения добавлен один внутренний комментарий на обращении №36;
новые исходящие письма ради повторения известной ошибки не отправлялись.

Полные сценарии BFCache, offline/reconnect и скрытия вкладки уже проверены
в предыдущей итерации на b421e755 (история Skaro от 12.10.2026). Их результаты
сохранены, длительные сценарии без причины повторно не запускались.

## Открытый критерий 6

Реальная отправка и связанный входящий ответ **не проверены**. В окружении
штатный ящик использует smtp.atelie-nord.ru и imap.atelie-nord.ru; оба имени
не разрешаются из backend-admin (`socket.gaierror`, Temporary failure in name
resolution). Демо-ящик mail.example.test также не разрешается и не заменяет
штатную почту. Прежние реальные попытки показывают только путь ошибки.
SMTP_ACCEPTED/UNKNOWN и входящий ответ проверены на уровне адресных тестов,
а не живой отправкой. Fake SMTP, подмена API, seed, сброс данных и смена
учётных данных не выполнялись. Этот критерий нельзя считать успешным.

## Команды

```powershell
docker compose exec -T frontend sh -c "cd /app/apps/internal-ui && npm run build"
docker compose exec -T web-chat sh -c "cd /app/apps/web-chat && npm run build"
docker compose exec -T backend-admin python manage.py check
docker compose exec -T backend-admin python manage.py makemigrations --check --dry-run
docker compose exec -T backend-admin pytest -q chatballs/conversations/test_email_ui_contract.py chatballs/conversations/test_email_merge_contracts.py chatballs/conversations/test_email_send_api.py chatballs/conversations/test_email_delivery.py chatballs/conversations/test_email_inbound.py chatballs/conversations/test_email_visitor_access.py chatballs/webchat/test_observations.py chatballs/conversations/test_site_field_manual_edits.py chatballs/conversations/test_chat_extras.py::CountersTests::test_contact_card_edit_from_contacts_page chatballs/conversations/test_chat_extras.py::CountersTests::test_contact_card_edit_from_dialog chatballs/i18n/tests.py::CatalogTests --reuse-db --tb=short -p no:cacheprovider
docker compose exec -T frontend sh -c "cd /app/apps/internal-ui && npx vitest run src/features/conversations/useComposerModel.test.tsx src/features/conversations/emailStatus.test.ts src/features/conversations/visitorState.test.ts src/features/conversations/feed.test.ts src/features/conversations/templateVariables.test.ts src/features/conversations/replyDraft.test.ts"
docker compose exec -T web-chat sh -c "cd /app/apps/web-chat && npx vitest run src/visitorSignals.test.ts src/participantAuthorship.test.tsx"
node --test tests/webchat/loader.test.cjs
```

Полный набор не запускался. Проверки воспроизводятся только в управляемом
штатном окружении этой задачи.

## Подключение следующей main

Во время проверки main продвинулась до 923412f6 (после 37233546).
В ветку T-076 подключены оба опубликованных серверных результата: правила
обработки, подтверждения и напоминания. Единственный конфликт был в каталоге
i18n; сохранены словари обеих веток. Пустые merge-миграции
conversations/0046_merge_email_ui_rules и tenancy/0066_merge_email_ui_rules
соединяют новые ветви со схемой T-076. UI при этом не изменялся: успешные
фронтенд-сборки и тесты не повторялись.

Новый адресный прогон: **11 passed, 38.53 s**. Проверены единый срок ожидания
входящего EMAIL-ответа и отмена напоминания исходящим письмом; совместимость
передачи с версиями назначения; завершение диалога и анализ качества;
участники, отзыв прав до outbox, удаление предшественника и каталог i18n.
`docker compose build backend-admin`, Django check, makemigrations --check
--dry-run и Ruff прошли на окончательной версии.

На окончательном backend Playwright подтвердил восстановление WebSession
без повторного согласия, новый UUID документа и нумерацию с 1 после reload.
Две вкладки использовали разные UUID (2c9dd8bf… и dd08f551…) и независимую
нумерацию. Закрытие панели принято API (200): widget=closed, page=visible,
connection=connected, departure=unknown. Реальный переход вперёд принят
с новым UUID eb3e82c7… (200); быстрый возврат назад попал под штатный лимитер
(429), сессия сохранилась, форма согласия не вернулась. Лимитер не сбрасывался.
Последующие штатные heartbeat приняты (200), sequence продолжился до 23,
connection=connected, departure=unknown. В E2 вкладка «Письмо» отключена,
ссылка ведёт в contacts/39 с доступным полем Email; данные контакта не менялись.
Ошибки сети во время остановки/перезапуска среды и прежний HMR-контекст
не считались успешной проверкой; окончательный UI после полной загрузки
имеет три вкладки, сохранённые адрес/ящик и readiness БД/Redis, без ошибок JS.

```powershell
docker compose build backend-admin
docker compose exec -T backend-admin pytest -q chatballs/conversations/rules/test_email_reminder.py chatballs/conversations/rules/test_main_transitions.py chatballs/conversations/test_email_merge_contracts.py chatballs/conversations/test_email_inbound.py::EmailInboundTests::test_old_thread_deletion_keeps_successor_history chatballs/i18n/tests.py::CatalogTests --reuse-db --tb=short -p no:cacheprovider
```
