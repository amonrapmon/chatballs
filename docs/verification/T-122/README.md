# Проверка интеграции T-122

Проверено 2026-10-13 в штатном окружении `skaro-chatballs-t-122`.
Сохранённое слияние d9455204 зафиксировано в dbd8872e, затем подключена
актуальная main 3308ca2d (включает T-093, T-105 и отчёты поддержки).
Все почтовые функции и функции main сохранены; интерфейс относительно main
не менялся, browser-проверка к разрешению конфликтов не применяется.

## Результаты

- После первоначального разрешения: **130 passed, 1 skipped**, 212.87 s.
- После подключения новой main и объединения миграций: **37 passed, 1 skipped**, 49.21 s.
- Единственный пропуск в каждом прогоне: проверка frontend-каталога i18n,
  frontend не смонтирован в backend-контейнер. Backend-каталоги проверены.
- Сборка backend-admin, Django check, makemigrations --check --dry-run прошли.
- Ruff, git diff --check и проверка размеров изменённых Python-файлов прошли;
  файлов свыше 300 строк из-за работы T-122 нет.
- http://localhost:20150/api/v1/health/ready/:
  `{"status":"ok","checks":{"database":true,"redis":true}}`.
- Тесты используют изолированную Django test-БД и `--reuse-db`.
  Seed, внешние SMTP/API-серверы и изменения рабочих учётных данных не выполнялись.
- SMTP проверен на границе стандартного библиотечного клиента; физическая
  доставка внешнему адресату не проверялась. SMTP_ACCEPTED не означает доставку.

## Выполненные команды

```powershell
docker compose build backend-admin
docker compose exec -T backend-admin python manage.py check
docker compose exec -T backend-admin python manage.py makemigrations --check --dry-run
docker compose exec -T backend-admin pytest -q chatballs/conversations/test_email_send_api.py chatballs/conversations/test_email_delivery.py chatballs/conversations/test_email_inbound.py chatballs/conversations/test_email_concurrency.py chatballs/conversations/test_email_visitor_access.py chatballs/conversations/test_email_smtp_outcomes.py chatballs/conversations/test_email_transport.py chatballs/conversations/test_email_continuation_models.py chatballs/conversations/test_email_attempt_models.py chatballs/conversations/test_email_continuation_guards.py chatballs/conversations/test_email_merge_contracts.py chatballs/conversations/test_ingest_dedup.py chatballs/conversations/test_query_budget.py chatballs/conversations/test_inbound_media_errors.py chatballs/conversations/test_domain_event_sources.py chatballs/conversations/test_participant_workflow.py chatballs/conversations/test_supervisor_access.py chatballs/conversations/test_supervisor_realtime.py chatballs/i18n/tests.py chatballs/webchat/tests.py::PublicWebChatWidgetTests::test_voice_message_round_trip chatballs/webchat/tests.py::PublicWebChatWidgetTests::test_file_message_round_trip --reuse-db --tb=short -rs
docker compose exec -T backend-admin pytest -q chatballs/conversations/test_email_report_contracts.py chatballs/conversations/test_support_timeline.py chatballs/conversations/test_support_report.py chatballs/conversations/test_email_merge_contracts.py chatballs/conversations/test_email_inbound.py::EmailInboundTests::test_old_thread_deletion_keeps_successor_history chatballs/conversations/test_conversation_delete.py chatballs/i18n/tests.py --reuse-db --tb=short -rs
```

Полный набор не запускался. Успешный первоначальный прогон не повторялся;
дополнительный набор покрывает только новую совместимость миграций, отчётов,
каталога, прав почтового ответа и удаления предшественника.
