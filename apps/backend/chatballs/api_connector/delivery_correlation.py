"""Shared, source-scoped identity of Connector commands and provider replies."""

from django.db.models import Q

from chatballs.api_connector.payloads import ConnectorPayloadError
from chatballs.conversations.models import Message, MessageAuthor
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.native_mirror.models import PublicationStatus


def lock_current_connector(connection: Integration) -> Integration:
    """Serialize mirror, callback correlation, and Connector settings changes."""
    current = Integration.objects.select_for_update(of=("self",), no_key=True).select_related("channel").filter(
        pk=connection.pk, organization_id=connection.organization_id, provider=IntegrationProvider.API_CONNECTOR,
    ).first()
    if current is None:
        raise ConnectorPayloadError("not_found", 404)
    if current.secret != connection.secret:
        raise ConnectorPayloadError("unauthorized", 401)
    if not current.is_active or not current.channel or not current.channel.is_active:
        raise ConnectorPayloadError("forbidden", 403)
    return current


def lock_command_message(connection, *, conflict_code, **identity):
    # The worker may hold Conversation then Message, and never takes this lock.
    lock_current_connector(connection)
    candidates = Message.objects.select_for_update(of=("self",)).filter(
        Q(author_type=MessageAuthor.OPERATOR) | Q(
            author_type=MessageAuthor.AI,
            native_mirror_publication__status=PublicationStatus.CLAIMED,
        ),
        organization_id=connection.organization_id,
        conversation__connection_id=connection.pk,
        connector_delivery__has_key="commandId",
        **identity,
    )
    try:
        return candidates.get()
    except Message.DoesNotExist as error:
        raise ConnectorPayloadError("unknown_command", 409) from error
    except Message.MultipleObjectsReturned as error:
        raise ConnectorPayloadError(conflict_code, 409) from error


def check_provider_identity(connection, message, external_id, *, conflict_code):
    if not external_id:
        return
    previous_provider_id = message.connector_delivery.get("providerMessageId", "")
    if previous_provider_id and previous_provider_id != external_id:
        raise ConnectorPayloadError(conflict_code, 409)
    if Message.objects.filter(
        Q(connector_delivery__providerMessageId=external_id)
        | Q(external_id=external_id, connector_origin="EXTERNAL_OBSERVED"),
        organization_id=connection.organization_id,
        conversation__connection_id=connection.pk,
        conversation__external_chat_id=message.conversation.external_chat_id,
    ).exclude(pk=message.pk).exists():
        raise ConnectorPayloadError(conflict_code, 409)
