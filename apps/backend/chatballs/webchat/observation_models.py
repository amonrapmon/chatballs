"""Independent observations for each browser document in a WebSession."""

from django.db import models

from chatballs.tenancy.models import TenantRelationModel

WIDGET_STATES = ("unknown", "open", "closed")
PAGE_STATES = ("unknown", "visible", "hidden", "frozen", "resumed", "pagehide", "pageshow")
CONNECTION_STATES = ("unknown", "connected", "lost")


class VisitorObservation(TenantRelationModel):
    tenant_relation_fields = ("session",)
    session = models.ForeignKey(
        "webchat.WebSession", on_delete=models.CASCADE, related_name="observations",
    )
    tab_id = models.UUIDField()
    sequence = models.PositiveBigIntegerField()
    widget_state = models.CharField(max_length=16, default="unknown")
    page_state = models.CharField(max_length=16, default="unknown")
    connection_state = models.CharField(max_length=16, default="unknown")
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    widget_changed_at = models.DateTimeField(null=True, blank=True)
    page_changed_at = models.DateTimeField(null=True, blank=True)
    connection_changed_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "tab_id"], name="uniq_visitor_session_tab"),
            models.CheckConstraint(condition=models.Q(sequence__gte=1), name="visitor_sequence_positive"),
            models.CheckConstraint(condition=models.Q(widget_state__in=WIDGET_STATES), name="visitor_widget_valid"),
            models.CheckConstraint(condition=models.Q(page_state__in=PAGE_STATES), name="visitor_page_valid"),
            models.CheckConstraint(condition=models.Q(connection_state__in=CONNECTION_STATES), name="visitor_connection_valid"),
        ]
