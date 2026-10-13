# Проверка T-064

Штатное окружение `skaro-chatballs-t-064`, копия базы основной установки.
Frontend: http://localhost:20004; backend: http://localhost:20002.
Readiness через frontend подтвердил `database=true`, `redis=true`; Compose
подтвердил backend-app, backend-admin, frontend, postgres и redis.
В команду запуска через Skaro добавлен документированный backend-admin.
Демо-набор уже имел статус INSTALLED (931 записей); seed не выполнялся.

## Браузер с реальным API

Playwright MCP задачи, два независимых browser context. Использованы существующие
Елена Кузнецова (ADMIN) и Светлана Петрова (EMPLOYEE → SUPERVISOR) с документированным
паролем. Владелец отдельно разрешил назначение и отзыв в этой копии данных.
Пароли, TOTP, блокировки и обычное членство не менялись; аккаунты не сбрасывались.

- E2: через карточку назначена роль SUPERVISOR и контроль «Поддержки» (id 2),
  update вернул 200. Обычная группа осталась «Операторы» (id 1).
- E3: пустая область показывает предупреждение и не выдаёт доступ всей организации.
- E4: реальное отключение сети средствами браузера показало баннер ошибки,
  сохранило форму; после восстановления связи штатное сохранение прошло с 200.
  API-ответы не подменялись.
- K7: диалог 30 группы «Поддержка» доступен при отсутствии обычного членства.
  API выдал view/assign/transfer/participants/comment, `canControl=false`,
  `canReply=false`; ответа клиенту, взятия, закрытия, звонка и удаления нет.
  В дереве щит только у подконтрольной группы.
  На ширине 760 px меню содержит только передачу и открывает штатную форму;
  закрытие и спам отсутствуют. Запрос списка сотрудников этим аккаунтом — 403.
- Комментарий сохранён с 201, INTERNAL, автором Светланой и UUID операции.
  Назначен Игорь Савельев; карточка подтвердила assignee id 5 и version 1.
  Затем передано Елене с 200, инициатор id 4, version 2 и записью передачи id 1.
  Пустой штатный справочник причин настроен администратором через существующий UI:
  создана показанная в baseline причина «Вопрос по оплате» (201); seed не запускался.
- Подключена Наталья Фролова (201) с обязательной причиной. Подключение себя
  супервизором также прошло с 201. После принятия диалога ответственным сервер
  выдал участнику `canReply=true`, UI разрешил ответ без смены ответственного.
  Перед отзывом области собственное участие завершено с 200, чтобы проверить
  потерю именно управленческого доступа.
- K8: администратор отозвал «Поддержку» при открытом чате (update 200).
  Detail вернул 404 с собственным фактом отзыва из аудита: Елена Кузнецова,
  2026-10-13T20:51:38.085943Z. Баннер показал фактическое время 23:51,
  действия исчезли, редактор заблокирован. POST note после отзыва вернул 404.
  Contenteditable, редактирование заметки и добавление меток отсутствуют;
  состав (1 участник) и журнал (3 записи) остались без ошибок обновления.
- K9: после перехода к списку диалог 30 исчез; сессия сохранила SUPERVISOR,
  `groups=[1]`, `supervisedGroups=[]`, `supervisionCapabilities=[]`.
  После проверки через UI восстановлена исходная роль EMPLOYEE (200),
  `groups=[1]`, область пустая; email, блокировка, TOTP и требование смены пароля
  остались исходными. Проверка затронула только копию T-064.

Снимки в этом каталоге: `employee-assigned.png`, `employee-save-error.png`, `employee-empty-area.png`,
`supervisor-control.png`, `supervisor-participant.png`, `supervisor-revoked.png`,
`supervisor-empty-area.png`, `supervisor-mobile-menu.png`. `baseline-employees.png` — исходный дизайн-референс,
просмотренный отдельно через оригинальный runtime без HTTP-сервера.

## Исполняемые проверки

```powershell
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run build
docker compose exec -T frontend npm --workspace @chatballs/internal-ui run test -- src/auth/access.test.ts src/features/employees/model.test.ts src/features/conversations/supervision.test.ts src/features/conversations/useComposerModel.test.tsx src/features/conversations/useConversationList.test.ts src/features/conversations/useConversationEvents.test.tsx src/i18n/catalog.test.ts
docker compose exec -T backend-admin pytest chatballs/conversations/test_supervision_access_loss.py chatballs/conversations/test_supervisor_access.py --reuse-db -q
docker compose exec -T backend-admin python manage.py check
docker compose exec -T backend-admin ruff check chatballs/conversations/participant_access_loss.py chatballs/conversations/supervision_access_loss.py chatballs/conversations/test_supervision_access_loss.py
```

Сборка прошла (tsc и Vite; предупреждение существующих крупных chunks),
20 frontend-тестов и 21 серверный тест прошли; Django check и Ruff без ошибок.
Полный набор тестов не запускался, миграций нет. Новые проверки покрывают
разделение групп, запрет публичной отправки по одному контролю, отсутствие
административной навигации, собственный аудит, блокировку и tenant-изоляцию.

Изменённые компоненты имеют меньше 180 строк; API, состояние, подвиды и стили
разделены. Хук рабочего пространства сохраняет единую ответственность
координации; новые данные/проверки вынесены в supervision-модули. Большие
существующие i18n-каталоги получают только импорт отдельного словаря и удаление
служебной лексики в существующем тексте безопасности.
