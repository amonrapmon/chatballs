"""Status intersections. The caller supplies the agreed effective upper bound."""

from chatballs.identity.work_status_codes import WorkStatus
from chatballs.identity.work_status_intervals import work_status_intersections


def status_durations(transitions, *, start, end, effective_end, tracking_from=None):
    if tracking_from is not None:
        # Before durable stops, an unblocked membership can hide a prior cut.
        # Do not fabricate continued time from such a pre-tracking selection.
        transitions = [item for item in transitions if item.changed_at >= tracking_from]
    available = transitions[0].changed_at if transitions else None
    observed = {status: 0.0 for status in WorkStatus.values}
    current = {status: 0 for status in WorkStatus.values}
    intervals = list(work_status_intersections(transitions, start=start, end=min(end, effective_end)))
    for interval in intervals:
        observed[interval.status] += (interval.end - interval.start).total_seconds()
        current[interval.status] += int(interval.current)
    complete = available is not None and start >= available
    return {"availableFrom": available.isoformat() if available else None, "complete": complete,
            "durationUnit": "seconds", "intervals": [
                {"status": item.status, "version": item.version, "from": item.start.isoformat(),
                 "to": item.end.isoformat(), "seconds": (item.end - item.start).total_seconds(),
                 "current": item.current} for item in intervals
            ], "values": {
                status: {"seconds": round(value, 6) if complete else None,
                         "observedSeconds": round(value, 6), "currentIntervals": current[status]}
                for status, value in observed.items()
            }}
