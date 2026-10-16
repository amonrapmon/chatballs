"""Work time only for the current permitted team; no conversation attribution."""

from collections import defaultdict

from django.db.models import F

from chatballs.conversations.support_status_intervals import status_durations
from chatballs.identity.group_models import EmployeeGroupMember
from chatballs.identity.work_status_codes import WorkStatus
from chatballs.identity.work_status_models import WorkStatusOperation


def team_status_report(*, organization_id, members, filters, upper, tracking_from):
    eligible = {member.pk for member in members}
    if filters.group is not None:
        eligible &= set(EmployeeGroupMember.objects.filter(
            organization_id=organization_id, employee_id__in=eligible, group_id=filters.group,
        ).values_list("employee_id", flat=True))
    history = defaultdict(list)
    for item in WorkStatusOperation.objects.filter(
        organization_id=organization_id, membership_id__in=eligible,
    ).exclude(previous_status=F("status")).order_by("membership_id", "version"):
        history[item.membership_id].append(item)
    rows = {}
    details = []
    for member in members:
        selected = member.pk in eligible
        durations = status_durations(history[member.pk] if selected else [], start=filters.start,
                                     end=filters.end, effective_end=upper, tracking_from=tracking_from)
        intervals = durations.pop("intervals")
        details.extend({"employee": member.user_id, **interval} for interval in intervals)
        rows[member.user_id] = {**durations, "included": selected,
                               "stopPolicy": "cut_at_block", "blockedAt": member.blocked_at.isoformat() if member.blocked_at else None}
    included = [row for row in rows.values() if row["included"]]
    complete = all(row["complete"] for row in included)
    total = {"complete": complete, "durationUnit": "seconds", "employees": len(included),
             "stopPolicy": "cut_at_block", "values": {}}
    for status in WorkStatus.values:
        observed = round(sum(row["values"][status]["observedSeconds"] for row in included), 6)
        total["values"][status] = {"seconds": observed if complete else None, "observedSeconds": observed,
                                   "currentIntervals": sum(row["values"][status]["currentIntervals"] for row in included)}
    return rows, total, details
