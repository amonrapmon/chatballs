"""Validated, channel-neutral contracts for external operator replies.

An adapter must authenticate the originating connection and supply stable
provider event/message IDs. This module never treats customer inbound as a
native operator reply and never persists or sends messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MirrorOutcome(StrEnum):
    STORED = "stored"
    DUPLICATE = "duplicate"
    SELF_ECHO = "self_echo"
    RETRYABLE = "retryable"
    UNMATCHED = "unmatched"
    IGNORED = "ignored"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True, slots=True)
class NativeReplyEvent:
    integration_id: int
    provider: str
    source_id: str
    external_chat_id: str
    event_id: str
    external_message_id: str
    occurred_at: datetime
    text: str
    external_reply_to_id: str = ""

    def __post_init__(self) -> None:
        if type(self.integration_id) is not int or self.integration_id <= 0:
            raise ValueError("integration_id must be a positive integer")
        for field in ("provider", "source_id", "external_chat_id",
                      "event_id", "external_message_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must be a non-empty string")
        if not isinstance(self.occurred_at, datetime) or (
            self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() is None
        ):
            raise ValueError("occurred_at must be timezone-aware")
        if not isinstance(self.external_reply_to_id, str):
            raise ValueError("external_reply_to_id must be a string")

    @property
    def dedup_key(self) -> tuple[int, str]:
        """Provider event IDs are scoped to the integration, never globally."""
        return (self.integration_id, self.event_id)


@dataclass(frozen=True, slots=True)
class MirrorResult:
    outcome: MirrorOutcome
    message_id: int | None = None
    retryable: bool = False
