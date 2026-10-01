---
id: T-003
title: Разобраться с признаком режима поставки CLOUD / SELF_HOSTED
status: todo
depends_on: []
spec: "0005"
created: 2026-09-28
archived: true
---

## Цель

Устранить расхождение: в `README.md`, `scripts/start.sh`, `scripts/start.ps1` и бэкенде встречается признак режима поставки `CLOUD` / `SELF_HOSTED`, который не описан ни одним решением, а managed-облако в продукт не входит.

## Критерии приёмки

- [ ] Владелец решил, нужен ли признак после отказа от managed-облака
- [ ] Признак либо описан в спецификации установки с назначением и влиянием на поведение, либо удалён из README, скриптов и кода
- [ ] Установка по-прежнему не требует ни одной переменной окружения

## Заметки

Упоминания найдены в `apps/backend/chatballs_backend/settings_base.py`, `chatballs/platform/provisioning_models.py`, `chatballs/api/permissions.py`, `scripts/start.sh`, `scripts/start.ps1`. Источник провижининга `SELF_HOSTED_SETUP` используется при создании организаций. Решение за владельцем.
