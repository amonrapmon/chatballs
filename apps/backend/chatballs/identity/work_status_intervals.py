"""Half-open intervals over transitions, without fabricating pre-feature time.

    This is status duration, not attendance or payable hours. A recorded block
    permanently ends the selected interval; unblocking does not resume it.
"""

from dataclasses import dataclass
from datetime import datetime

from rest_framework.exceptions import ValidationError

from chatballs.i18n import t
from chatballs.identity.work_status_services import own_work_status_history


@dataclass(frozen=True, slots=True)
class WorkStatusInterval:
    status: str
    version: int
    start: datetime
    end: datetime
    current: bool = False


def work_status_intersections(history, *, start, end):
    for index, operation in enumerate(history):
        next_start = history[index + 1].changed_at if index + 1 < len(history) else end
        stopped_at = getattr(operation, "stopped_at", None)
        left, right = max(start, operation.changed_at), min(end, next_start, stopped_at or end)
        if left < right:
            current = right == end and next_start >= end and (stopped_at is None or stopped_at > end)
            yield WorkStatusInterval(operation.status, operation.version, left, right, current)


def own_work_status_intervals(*, context, start, end):
    if (
        not isinstance(start, datetime) or not isinstance(end, datetime)
        or start.utcoffset() is None or end.utcoffset() is None or start >= end
    ):
        raise ValidationError(t("work_status.period_invalid"))
    history = own_work_status_history(context=context)
    return list(work_status_intersections(history, start=start, end=end))
