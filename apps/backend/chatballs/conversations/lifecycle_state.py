"""Shared state transition for an authorized, already locked conversation."""

from chatballs.conversations.models import ControlMode, ExpectedResponder
from chatballs.conversations.queue import leave_queue
from chatballs.conversations.service_common import _require_open


def finish_locked(conversation, lifecycle):
    _require_open(conversation)
    conversation.lifecycle = lifecycle
    conversation.control_mode = ControlMode.PAUSED
    conversation.assigned_operator = None
    conversation.expected_responder = ExpectedResponder.NOBODY
    leave_queue(conversation)
    conversation.save(update_fields=[
        "lifecycle", "control_mode", "assigned_operator", "expected_responder", "waiting_since",
    ])
    return conversation
