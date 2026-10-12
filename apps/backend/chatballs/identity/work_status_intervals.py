"""Half-open intervals over transitions, without fabricating pre-feature time.

    This is status duration, not attendance or payable hours. Blocking does not
    truncate history here; that policy belongs to the future reporting integration.
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


def own_work_status_intervals(*, context, start, end):
    if (
        not isinstance(start, datetime) or not isinstance(end, datetime)
        or start.utcoffset() is None or end.utcoffset() is None or start >= end
    ):
        raise ValidationError(t("work_status.period_invalid"))
    history = own_work_status_history(context=context)
    intervals = []
    for index, operation in enumerate(history):
        next_start = history[index + 1].changed_at if index + 1 < len(history) else end
        left, right = max(start, operation.changed_at), min(end, next_start)
        if left < right:
            intervals.append(WorkStatusInterval(operation.status, operation.version, left, right))
    return intervals
