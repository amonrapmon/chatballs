"""Ordered visitor signals. This module never changes a conversation or outbox."""

from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from chatballs.i18n import t
from chatballs.webchat.models import WebSession
from chatballs.webchat.observation_models import VisitorObservation

HEARTBEAT_INTERVAL_SECONDS = 30
HEARTBEAT_TIMEOUT_SECONDS = 90
MAX_TABS_PER_SESSION = 64
SIGNALS = {
    "widget_open": ("widget_state", "open"),
    "widget_close": ("widget_state", "closed"),
    "page_visible": ("page_state", "visible"),
    "page_hidden": ("page_state", "hidden"),
    "page_freeze": ("page_state", "frozen"),
    "page_resume": ("page_state", "resumed"),
    "page_hide": ("page_state", "pagehide"),
    "page_show": ("page_state", "pageshow"),
    "heartbeat": ("connection_state", "connected"),
    "connection_lost": ("connection_state", "lost"),
}


def parse_signal(data):
    try:
        tab_id = UUID(data["tabId"]) if isinstance(data["tabId"], str) else None
        sequence = data["sequence"]
        kind = data["kind"]
        valid = (
            tab_id is not None and tab_id.int != 0
            and type(sequence) is int and 1 <= sequence <= 2**63 - 1
            and isinstance(kind, str) and kind in SIGNALS
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise ValidationError({"detail": t("webchat.observation_invalid")})
    return tab_id, sequence, kind


@transaction.atomic
def record_signal(session: WebSession, data) -> tuple[bool, VisitorObservation]:
    tab_id, sequence, kind = parse_signal(data)
    # Serialize creation as well as updates: two concurrent first signals must
    # not create duplicate tabs, and the lower sequence must never win a race.
    WebSession.objects.select_for_update().get(pk=session.pk, organization_id=session.organization_id)
    rows = VisitorObservation.objects.filter(session=session, organization_id=session.organization_id)
    row = rows.filter(tab_id=tab_id).first()
    if row is not None and sequence <= row.sequence:
        return False, row
    if row is None:
        if rows.count() >= MAX_TABS_PER_SESSION:
            raise ValidationError({"detail": t("webchat.observation_tabs_limit")})
        row = VisitorObservation(session=session, tab_id=tab_id)
    row.sequence = sequence
    row.received_at = timezone.now()
    field, value = SIGNALS[kind]
    expired = field == "connection_state" and row.heartbeat_at and (
        row.received_at - row.heartbeat_at >= timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)
    )
    if getattr(row, field) != value or expired:
        setattr(row, field.replace("_state", "_changed_at"), row.received_at)
    setattr(row, field, value)
    if kind == "heartbeat":
        row.heartbeat_at = row.received_at
    row.save()
    return True, row


def observation_payload(row: VisitorObservation, *, now=None) -> dict:
    now = now or timezone.now()
    connection = row.connection_state
    connection_changed_at = row.connection_changed_at
    if connection == "connected" and (
        row.heartbeat_at is None
        or now - row.heartbeat_at >= timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)
    ):
        connection = "lost"
        connection_changed_at = row.heartbeat_at + timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS) if row.heartbeat_at else None
    return {
        "tabId": str(row.tab_id), "sequence": row.sequence,
        "widget": row.widget_state, "page": row.page_state,
        "connection": connection, "departure": "unknown",
        "receivedAt": row.received_at.isoformat(),
        "heartbeatAt": row.heartbeat_at.isoformat() if row.heartbeat_at else None,
        "widgetChangedAt": row.widget_changed_at.isoformat() if row.widget_changed_at else None,
        "pageChangedAt": row.page_changed_at.isoformat() if row.page_changed_at else None,
        "connectionChangedAt": connection_changed_at.isoformat() if connection_changed_at else None,
    }


def session_observations(session: WebSession) -> dict:
    now = timezone.now()
    return {
        "heartbeatIntervalSeconds": HEARTBEAT_INTERVAL_SECONDS,
        "heartbeatTimeoutSeconds": HEARTBEAT_TIMEOUT_SECONDS,
        "tabs": [observation_payload(row, now=now) for row in
                 VisitorObservation.objects.filter(
                     session=session, organization_id=session.organization_id,
                 ).order_by("tab_id")],
    }
