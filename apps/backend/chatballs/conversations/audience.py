"""Audience is selected before pagination; comments never share Message ids."""

from enum import StrEnum


class ConversationAudience(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
