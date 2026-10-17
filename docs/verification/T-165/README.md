# Проверка оформления виджета и выбора сотрудников

16.10.2026, штатное окружение Skaro `skaro-chatballs-t-165`:
frontend `http://localhost:20004`, backend `http://localhost:20002`,
web-chat `http://localhost:20005`. Frontend и web-chat используют
`VITE_DEV_API_TARGET=http://backend-app:8000`. Readiness через frontend:
`status=ok`, `database=true`, `redis=true`; PostgreSQL, Redis и оба backend healthy.
Для штатных тестов через configure_environment добавлен backend-admin.
После окончательных изменений выполнен start_environment с пересборкой образов.

Использована disposable-копия штатных данных, установленные демо-сотрудники
и их загруженные фотографии. Учётные данные, роли и права не изменялись;
seed, bootstrap, mock API, fake backend и временные серверы не использовались.
Настройки и переписка менялись только штатным интерфейсом копии задачи.

## Иконка

В штатной форме создана WEB-интеграция 23 без ИИ-агента, с текущими origins
окружения. Иконкой служит существующий `shared/branding/logo-sunset.svg`.
Проверены сохранение и перезагрузка реального опубликованного виджета:

- пустая иконка шапки наследует загруженную иконку кнопки;
- собственная иконка шапки имеет другой URL и совпадает с предпросмотром;
- «Без иконки» убирает знак: первый элемент шапки — название;
- сброс шапки восстанавливает наследование, сброс кнопки — штатный знак;
- в режиме «Только операторы» сохранённая собственная иконка остаётся видимой:
  публичная конфигурация содержит `available=true`, `autonomous=false`.

Скриншоты: `appearance-saved-preview.png`, `widget-inherited-icon.png`,
`widget-no-icon.png`, шапка на скриншотах переписки.
Существующая интеграция 5 первоначально исследовалась с сохранённым старым
origin другого окружения; недоступный по этому origin виджет не засчитывался
как проверка. Финальный сценарий выполнен на интеграции 23.

## Авторы сообщений

В диалоге 32 клиент написал через опубликованный виджет. Елена Кузнецова
приняла обращение и ответила. Затем штатной формой подключена Анна Ким;
она вошла в отдельном браузерном контексте существующей учётной записью
и ответила с пометкой «Вы участник». Ответственный остался Еленой.
Оба новых ответа появились в виджете с именем конкретного автора и разными
загруженными фотографиями 32×32 px. Перезагрузка восстановила оба имени,
сообщения и фотографии. См. `colleague-response.png`,
`widget-two-authors-live.png`, `widget-two-authors-history.png`.

Фото выдаётся по токену web-сессии и ID видимого клиентского сообщения,
без публичного URL профиля или пути хранилища. Сервер проверяет membership
автора в организации сессии. Внутренние события, чужие сообщения,
сообщения не сотрудника и запросы без действующего токена фото не раскрывают.
Ответы фото имеют `Cache-Control: private, no-store` и `nosniff`.
При отсутствии/ошибке фото используется существующий буквенный аватар сотрудника.

## Геометрия

До исправления computed styles меню: `display=block`, `text-align=left`,
унаследованный `line-height=17px`. Причина — общее правило меню для вложенных
span. В форме подключения flex уже работал; фотографии были загружены.
Кнопки до исправления: 30 и 38 px из-за min-height общей primary-button.

После исправления общие стили аватара вынесены из большого context.css
в small-avatar.css; для меню явно сохранён flex. Размер 22×22 px,
фотографии круглые, точка присутствия 8×8 px со смещением 2 px наружу.
В форме передачи сохранён размер 30×30 px. См. `assignee-geometry.json`,
`assignee-menu.png`, `transfer-avatars.json`, `transfer-avatars.png`.

`measure-avatars.js` выполнен через Playwright MCP на настоящей странице
с открытыми формой и меню. Геометрические пробы «И»/«ИС» временно заменяют
только DOM-содержимое существующего аватара и сразу восстанавливают его;
данные сотрудников и ответы API не меняются. Во всех трёх местах (закрытое
поле, меню, подключение) получены `dy=0`, `dx=-0.0078125 px` для одной и двух букв.

Обе кнопки имеют 30 px, padding `0 12px`, gap 8 px, margin-top 10 px — U2/U3.
Проверены отключённая кнопка, выбор сотрудника, busy при настоящем запросе,
ошибка и повторная попытка. Для ошибки кратко включён offline браузера;
сеть восстановлена в finally, ответы API не подменялись. «Повторить» также
30 px; успешный повтор подключил Игоря. См. `form-disabled.json`,
`participant-form.png`, `participant-retry.png`.

## Автоматические проверки

```powershell
docker compose exec -T web-chat npm run build
docker compose exec -T web-chat npm test -- src/widgetAppearance.test.tsx src/participantAuthorship.test.tsx src/operatorMode.test.tsx --testTimeout=30000
docker compose exec -T backend-admin pytest -q chatballs/webchat/test_internal_record_access.py --reuse-db --tb=short
docker compose exec -T backend-admin python manage.py check
docker compose exec -T backend-admin python -m ruff check --select E,F,I,UP,B,DJ --ignore DJ001,E501 --target-version py312 chatballs/webchat/author_avatars.py chatballs/webchat/author_avatar_views.py chatballs/webchat/message_history.py chatballs/webchat/urls.py chatballs/webchat/test_internal_record_access.py
git diff --check
```

Сборка web-chat успешна; frontend — 8 passed, backend — 8 passed;
Ruff — all checks passed. Полные наборы не запускались. Первый backend-прогон
выявил ошибки самих новых тестов (запрещённая БД чужая связь и преждевременное
закрытие потокового ответа); после исправления весь затронутый файл прошёл.
Backend выполнялся только с --reuse-db. Сборка internal-ui автоматически
не запускалась: его изменения ограничены CSS и импортом этого CSS.

Новые модули отвечают отдельно за выбор автора, выдачу фото и стили аватара;
изменённые компоненты меньше 180 строк, остальные новые/дополненные модули
меньше 300 строк. Большой context.css сокращён, новых ответственностей в нём нет.
DRY/SRP/NO GOD FILES проверены; новый layout, изображения и состояния не добавлены.
