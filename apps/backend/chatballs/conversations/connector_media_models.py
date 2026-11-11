"""Source-scoped identity for one independently announced inbound media message.

The native Message remains the authoritative content/status and attachment owner.
No provider URLs or credentials are stored here.
"""
from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class ConnectorMediaIngest(TenantRelationModel):
    tenant_relation_fields = ("integration", "message")
    integration = models.ForeignKey(
        "integrations.Integration", on_delete=models.PROTECT,
        related_name="connector_media_ingests",
    )
    message = models.OneToOneField(
        "conversations.Message", on_delete=models.CASCADE,
        related_name="connector_media_ingest",
    )
    external_chat_id = models.CharField(max_length=128)
    external_message_id = models.CharField(max_length=128)
    part_index = models.PositiveSmallIntegerField(default=0)
    announce_event_id = models.CharField(max_length=256)
    announce_fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["integration", "external_chat_id", "external_message_id", "part_index"],
                name="uniq_connector_media_source_part",
            ),
            models.CheckConstraint(
                condition=models.Q(part_index__lte=9),
                name="connector_media_max_ten_parts",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "integration"], name="conv_media_tenant_route"),
        ]
