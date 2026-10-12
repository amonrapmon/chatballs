"""Canonical visible-message scope for user timelines and AI context.

Suppressed AI replies remain in the database for diagnostics, but they are
not part of the conversation that the customer or operator actually saw.
"""

from __future__ import annotations

from django.db.models import QuerySet

from chatballs.conversations.models import Message
from chatballs.native_mirror.models import PublicationStatus


def visible_messages(queryset: QuerySet[Message]) -> QuerySet[Message]:
    return queryset.exclude(
        native_mirror_publication__status=PublicationStatus.SUPPRESSED,
    )
