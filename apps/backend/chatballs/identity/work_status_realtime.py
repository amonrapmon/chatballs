"""Invalidation only; REST returns the authorized current snapshot."""

from chatballs.realtime import publish

WORK_STATUS_EVENT = "work_status.changed"


def work_status_group(organization_id):
    return f"work_status.{organization_id}"


def notify_work_status_changed(organization_id, user_id):
    publish(work_status_group(organization_id), {"type": WORK_STATUS_EVENT, "userId": user_id})
