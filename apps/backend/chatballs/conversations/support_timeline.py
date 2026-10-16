"""Pure timeline reduction. No presence, current assignment or message text."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    metric: str
    start: object
    end: object
    dimension: object
    employee: int | None
    current: bool = False


def conversation_observations(events, incoming, end):
    observations = []
    accepted_operations = {event.operation_id for event in events if event.event_type == "ACCEPTED"}
    queue = processing = first = pending = ai_pending = None
    last_dimension = None
    last_responsible = None
    replied = False
    human_cycle = False

    def duration(metric, state, stop, employee=None, current=False):
        if state is not None:
            start, dimension, owner = state
            observations.append(Observation(metric, start, stop, dimension,
                                            owner if employee is None else employee, current))

    # Facts use server sequence for ties; incoming messages precede their facts.
    timeline = [(event.occurred_at, 1, event.sequence, event) for event in events]
    timeline.extend((message.created_at, 0, message.pk, message) for message in incoming)
    for at, _, _, item in sorted(timeline, key=lambda row: row[:3]):
        if at >= end:
            break
        kind = getattr(item, "event_type", None)
        # Mail continuation also records the customer's public reply. Its
        # message already supplies incoming timing; it is no agent answer.
        if kind == "PUBLIC_REPLY" and item.actor_kind == "CONTACT":
            continue
        if kind is None:
            if last_dimension is not None and human_cycle:
                if pending is None:
                    pending = (at, last_dimension, last_responsible)
            if ai_pending is None:
                ai_pending = at
            continue
        event = item
        if kind in {"ASSIGNED", "TRANSFERRED", "ACCEPTED"}:
            if kind == "TRANSFERRED":
                observations.append(Observation("transferred", at, at, event, last_responsible))
                if event.responsible_id is not None:
                    observations.append(Observation("receivedTransfers", at, at, event, event.responsible_id))
            duration("handling", processing, at)
            processing = None
            last_responsible = event.responsible_id
        if kind == "QUEUE_ENTERED":
            human_cycle = True
            duration("handling", processing, at)
            processing = None
            if queue is None:
                queue = (at, event, event.responsible_id)
                first = queue
                replied = False
        if kind == "ACCEPTED":
            human_cycle = True
            observations.append(Observation("accepted", at, at, event, event.responsible_id))
            duration("waiting", queue, at, event.responsible_id)
            queue = None
            processing = (at, event, event.responsible_id)
        if kind == "QUEUE_EXITED":
            if event.operation_id not in accepted_operations:
                duration("waiting", queue, at)
                queue = None
                duration("handling", processing, at)
                processing = first = pending = None
                human_cycle = False
        if kind == "PUBLIC_REPLY":
            human = event.actor_kind == "HUMAN"
            observations.append(Observation("humanReplies" if human else "aiReplies", at, at,
                                            event, event.initiated_by_id if human else None))
            if human:
                if first is not None:
                    duration("firstResponse", first, at, event.initiated_by_id)
                    first = None
                elif replied:
                    duration("subsequentResponse", pending, at, event.initiated_by_id)
                pending = None
                ai_pending = None
                replied = True
            else:
                if ai_pending is not None:
                    duration("aiResponse", (ai_pending, event, None), at)
                ai_pending = None
        if kind == "CLOSED":
            observations.append(Observation("completed", at, at, event, event.responsible_id))
            duration("waiting", queue, at)
            duration("handling", processing, at)
            queue = processing = first = pending = ai_pending = None
            human_cycle = False
        last_dimension = event
        if kind not in {"PUBLIC_REPLY", "QUEUE_EXITED"}:
            last_responsible = event.responsible_id
    duration("waiting", queue, end, current=True)
    duration("handling", processing, end, current=True)
    duration("firstResponse", first, end, current=True)
    if replied and first is None:
        duration("subsequentResponse", pending, end, current=True)
    if ai_pending is not None and last_dimension is not None:
        duration("aiResponse", (ai_pending, last_dimension, None), end, current=True)
    return observations
