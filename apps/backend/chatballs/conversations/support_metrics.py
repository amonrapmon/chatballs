"""Aggregate event timestamps and intersect half-open duration intervals."""

COUNTERS = ("accepted", "completed", "transferred", "receivedTransfers", "humanReplies", "aiReplies")
DURATIONS = ("waiting", "handling", "firstResponse", "subsequentResponse", "aiResponse")
UNIQUE = {"accepted", "completed"}


class Metrics:
    def __init__(self):
        self.counts = {key: 0 for key in COUNTERS}
        self.dialogs = {key: set() for key in UNIQUE}
        self.durations = {key: {"seconds": 0, "samples": 0, "current": 0} for key in DURATIONS}

    def add(self, observation, conversation_id, filters, *, employee=None):
        owner = observation.employee
        if employee is not None and owner != employee:
            return None
        if not filters.matches(observation.dimension, employee=owner):
            return None
        key = observation.metric
        if key in COUNTERS:
            if not filters.start <= observation.start < filters.end:
                return None
            self.counts[key] += 1
            if key in UNIQUE:
                self.dialogs[key].add(conversation_id)
            return None
        left, right = max(filters.start, observation.start), min(filters.end, observation.end)
        if left >= right:
            return None
        seconds = (right - left).total_seconds()
        self.durations[key]["seconds"] += seconds
        self.durations[key]["samples"] += 1
        self.durations[key]["current"] += int(observation.current)
        return {"conversationId": conversation_id, "metric": key, "employee": owner,
                "group": observation.dimension.group_id, "connection": observation.dimension.connection_id,
                "transport": observation.dimension.transport, "from": left.isoformat(), "to": right.isoformat(),
                "seconds": seconds, "current": observation.current}

    def payload(self, complete, *, counters_complete=None, include_observed=False):
        counters_complete = complete if counters_complete is None else counters_complete
        completeness = {key: counters_complete for key in COUNTERS}
        completeness.update({key: complete for key in DURATIONS})
        observed = {**self.counts, **{key: len(value) for key, value in self.dialogs.items()}}
        # An observed event is reliable even when earlier events are missing.
        # Without coverage, an unobserved count is unknown rather than zero.
        values = {key: value if counters_complete or (include_observed and value) else None
                  for key, value in observed.items()}
        for key, value in self.durations.items():
            seconds = round(value["seconds"], 6)
            measured = (complete or include_observed) and value["samples"]
            duration = {"seconds": seconds if complete or measured else None, "observedSeconds": seconds,
                        "samples": value["samples"], "currentIntervals": value["current"]}
            if key.endswith("Response"):
                duration["seconds"] = seconds if measured else None
                duration["meanSeconds"] = round(seconds / value["samples"], 6) if measured else None
            values[key] = duration
        return {"complete": complete, "completeByMetric": completeness, "values": values, "observedCounts": observed}
