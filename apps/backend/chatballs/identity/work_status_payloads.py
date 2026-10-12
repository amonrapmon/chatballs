"""Availability stays separate from technical presence in every payload."""


def status_payload(membership):
    return {
        "status": membership.work_status,
        "version": membership.work_status_version,
        "changedAt": stamp(membership.work_status_changed_at),
    }


def stamp(value):
    return value.isoformat() if value is not None else None


def operation_payload(operation):
    return {
        "operationId": str(operation.operation_id),
        "previousStatus": operation.previous_status,
        "status": operation.status,
        "version": operation.version,
        "changedAt": stamp(operation.changed_at),
        "recordedAt": stamp(operation.recorded_at),
        "changed": operation.changed,
    }
