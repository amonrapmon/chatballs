"""Explicit instants and historical dimensions shared by every report format."""

from dataclasses import dataclass
from datetime import UTC
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from chatballs.conversations.domain_event_models import ConversationEventTransport
from chatballs.i18n import t


@dataclass(frozen=True)
class ReportFilters:
    start: object
    end: object
    timezone: str
    employee: int | None = None
    group: int | None = None
    connection: int | None = None
    transport: str | None = None

    def matches(self, dimension, *, employee=None):
        return all((
            self.employee is None or self.employee == employee,
            self.group is None or self.group == dimension.group_id,
            self.connection is None or self.connection == dimension.connection_id,
            self.transport is None or self.transport == dimension.transport,
        ))

    def payload(self):
        return {"from": self.start.isoformat(), "to": self.end.isoformat(),
                "timezone": self.timezone, "employee": self.employee, "group": self.group,
                "connection": self.connection, "transport": self.transport}


def parse_filters(params):
    allowed = {"from", "to", "timezone", "employee", "group", "connection", "transport"}
    if set(params) - allowed or any(len(params.getlist(k)) != 1 for k in params if hasattr(params, "getlist")):
        raise ValidationError(t("support_stats.filters_invalid"))
    try:
        zone = params["timezone"]
        ZoneInfo(zone)
        start, end = (parse_datetime(params[key]) for key in ("from", "to"))
        if start is None or end is None or start.utcoffset() is None or end.utcoffset() is None or start >= end:
            raise ValueError
        dimensions = {}
        for key in ("employee", "group", "connection"):
            raw = params.get(key)
            if raw is not None:
                if not str(raw).isascii() or not str(raw).isdigit() or int(raw) <= 0:
                    raise ValueError
                dimensions[key] = int(raw)
        transport = params.get("transport")
        if transport is not None and transport not in ConversationEventTransport.values:
            raise ValueError
    except (KeyError, ValueError, TypeError, ZoneInfoNotFoundError, OverflowError) as error:
        raise ValidationError(t("support_stats.filters_invalid")) from error
    return ReportFilters(start.astimezone(UTC), end.astimezone(UTC), zone, transport=transport, **dimensions)
