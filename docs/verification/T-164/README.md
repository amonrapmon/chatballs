# Проверка режима организации

Проверка 16.10.2026 в штатном окружении Skaro `skaro-chatballs-t-164`.
Frontend: `http://localhost:20010`, API: `http://localhost:20008`,
виджет: `http://localhost:20011`. Frontend proxy указывает на `backend-app`
этого Compose-проекта. Readiness через frontend вернул HTTP 200,
`database=true`, `redis=true`; оба backend, PostgreSQL и Redis healthy,
`backend-admin`, worker и worker-events запущены.

Использован установленный демо-набор и существующий ADMIN из документированного
манифеста. Seed, bootstrap, смена паролей, ролей или других доступов не
выполнялись. Проверочная WEB-интеграция и сообщения созданы штатным интерфейсом
в disposable-копии данных задачи. Mock API, fake backend и временные серверы
не использовались. Изоляция проверена также под `chatballs_runtime_app`.

## Сборки и статические проверки

```powershell
docker compose exec -T frontend npm run build
docker compose exec -T web-chat npm run build
docker compose exec -T backend-admin python manage.py check
docker compose exec -T backend-admin python manage.py makemigrations --check --dry-run
```

Обе сборки успешны. Vite предупреждает о размере существующих крупных chunks.
Django: ошибок нет; дополнительных миграций не обнаружено. Ruff проверен
на изменённых и новых Python-файлах; `git diff --check` без ошибок.

## Затронутое поведение backend

```powershell
docker compose exec -T backend-admin pytest -q chatballs/identity/test_operation_modes.py chatballs/identity/test_administration_api.py chatballs/identity/test_operation_mode_migration.py chatballs/conversations/test_operation_mode_turns.py chatballs/conversations/test_operation_mode_delivery_race.py chatballs/conversations/test_ai_turn.py chatballs/integrations/test_operator_connections.py chatballs/webchat/tests.py chatballs/i18n/tests.py chatballs/conversations/tests.py::ContactShareIngestTests chatballs/ai/test_agent_cards.py chatballs/conversations/test_voice_ai_and_features.py chatballs/conversations/test_clients_list.py chatballs/conversations/test_authorization.py chatballs/ai/test_assistance_settings.py --reuse-db --tb=short
docker compose exec -T backend-admin pytest -q chatballs/conversations/test_operation_mode_realtime.py --reuse-db --tb=short
docker compose exec -T backend-admin pytest -q chatballs/calls/tests/test_flow.py::WebchatCallFlowTests --reuse-db --tb=short
```

Результаты: **129 passed, 1 skipped**; **1 passed**; **3 passed**.
Единственный skip — существующая условная проверка каталога i18n.
Полный набор не запускался. Тестовая схема обновлялась штатным pytest-django
для добавленных полей; все запуски с `--reuse-db`, без `--create-db`.

Проверены OWNER/ADMIN и отказ сотруднику/чужому участнику, RLS, идемпотентность
режима и аудит, сохранение очереди/времени/назначений/закрытых диалогов,
входящие пяти транспортов, отсутствие агента в обоих режимах, отсутствие
автономных заданий в операторском режиме, WEB-публикация, origins, сессия,
текст/файл/голосовое и история. Принятие, переключение, возврат к AI и
доставка проверены на конкурентных соединениях PostgreSQL. Проверены
отбрасывание завершившегося старого хода и повторной доставки после быстрого
выключения-включения, отмена после claim и подавление thinking.

Миграционный тест убирает новые поля и вновь применяет миграцию к существующим
записям тестовой БД: сохраняются реальные агенты, два подключения общего
маршрута, группа, публичный ключ, диалог и сообщение; исходный режим —
`AI_AGENTS`, версия 1. Рабочие данные окружения этим тестом не изменяются.
Звонки WEB проходят на Channel без AIAgent; настройки помощи независимы.

## Затронутое поведение frontend

```powershell
docker compose exec -T frontend npm test -- src/i18n/catalog.test.ts src/features/integrations/model.test.ts src/features/onboarding/operationModeSteps.test.ts --testTimeout=30000
docker compose exec -T frontend npm test -- src/i18n/catalog.test.ts --testTimeout=30000
docker compose exec -T web-chat npm test -- src/operatorMode.test.tsx src/consentText.test.tsx src/preChatModel.test.ts --testTimeout=30000
```

Результаты: **14 passed**, **11 passed**. В том числе проверено, что выбор
существующего агента не перезаписывает его группу группой старого подключения.
После нейтральной формулировки пустого списка чатов повторены каталог
(**3 passed**) и сборка frontend.
Повышен только timeout запуска на медленном
Windows bind mount; продуктовые таймауты не изменялись.

## Browser-проверка

Playwright MCP задачи использует реальный backend. Проверено сохранение обоих
режимов существующим администратором: HTTP 200, версия повышается при переходе.
Сохранённые пять агентов и старые общие маршруты остаются на прежних местах.
Чек-лист операторов содержит четыре доступных этому администратору шага,
без AI-провайдера, агента и знаний; при включении AI становится семишаговым.
Событие смены режима проходит штатный WebSocket с повторной авторизацией
membership; realtime-тест дополнительно доказывает отсутствие события у
соседней организации.

В существующей форме интеграций создан WEB без агента с группой «Операторы».
Интеграция 23 опубликована и получила собственный Channel; в колонке агента
показано отсутствие значения. Виджет открылся по публичному ключу, принял
согласие, создал сессию и принял сообщение. Показано штатное ожидание
сотрудника, без робота, AI-автора приветствия, «печатает» и фиктивной передачи.
Форма настроек виджета доступна без перехода в «Агенты».

Обращение 32 принято Еленой Кузнецовой штатной кнопкой «Взять диалог».
Ответ сотрудника отправлен через composer (HTTP 201) и появился у посетителя
с именем сотрудника и состоянием «Отвечает специалист». Переключения
`OPERATORS_ONLY → AI_AGENTS → OPERATORS_ONLY → AI_AGENTS → OPERATORS_ONLY`
повысили версию с 2 до 6; самостоятельный маршрут не стал автономным.
После последнего `start_environment` readiness вновь подтвердил БД и Redis.
Детали диалога вернули `HUMAN`, прежнего ответственного (id 2), группу 1,
`hasAgent=false`, `canReleaseToAi=false`. Перезагрузка страницы виджета
восстановила клиентское сообщение, событие принятия и ответ сотрудника.
В меню действий диалога нет «Вернуть ИИ»; обычные действия возврата в очередь,
закрытия и другие действия по правам доступны. После загрузки штатного
frontend браузер сообщает 0 ошибок и существующее предупреждение antd.
Раскрытая запись смены режима использует локализованные названия;
техническая версия остаётся в сохранённом payload, а не в пользовательском тексте.

## Структура

Новая политика режима, сериализация перехода, самостоятельные маршруты,
guard внешних AI-вызовов, состояние очереди AI, onboarding API и выбор шагов
вынесены по ответственностям. Форма интеграции разделена на представление,
hook и существующие поля выбора. AuditEvent вынесен из разросшегося identity
models; имена таблиц и контракт импортов сохранены. Новые продуктовые модули
меньше 180 строк; изменённые композиционные компоненты меньше 180 строк.
Существующие большие каталоги получают только импорт малого ru/en-модуля;
существующие тестовые файлы меняют непосредственно затронутые ожидания.

Функциональное описание и ограничение уже переданной внешней отправки:
[organization-operation-modes.md](../../organization-operation-modes.md).
