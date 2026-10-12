"""Доступность сотрудников для списка: рабочий статус и присутствие раздельно.

Статус хранится в членстве организации и меняется только самим сотрудником;
присутствие — технический признак «приложение открыто» (SPEC-0028, R-3, R-6).
Присутствие читается пачкой на всю страницу списка."""

from django.utils import timezone

from chatballs.identity.work_status_payloads import status_payload
from chatballs.presence import ONLINE_WITHIN_SECONDS, last_seen


def employee_availability(organization_id: int, memberships) -> dict[int, dict[str, object]]:
    """Поля `workStatus`, `online`, `lastSeenAt` по id пользователя."""
    rows = list(memberships)
    seen = last_seen(organization_id, [row.user_id for row in rows])
    now = timezone.now()
    return {
        row.user_id: {
            "workStatus": status_payload(row),
            "online": row.user_id in seen
            and (now - seen[row.user_id]).total_seconds() <= ONLINE_WITHIN_SECONDS,
            "lastSeenAt": seen[row.user_id].isoformat() if row.user_id in seen else None,
        }
        for row in rows
    }
