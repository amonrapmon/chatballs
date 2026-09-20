from __future__ import annotations

from django.utils import timezone

from chatballs.conversations.models import DeliveryStatus, Message

from .payloads import (
    GatewayPayloadError,
    UnsupportedGatewayDeliveryStatusError,
    parse_delivery_status_payload,
)
from .security import GatewayIngressError
from .services import gateway_authenticated_request


def accept_gateway_delivery_status(
    *, integration_id: int, authorization: str, payload: object
) -> None:
    def accept(context, integration) -> None:
        try:
            parsed = parse_delivery_status_payload(payload)
        except UnsupportedGatewayDeliveryStatusError as error:
            raise GatewayIngressError(422, str(error)) from error
        except GatewayPayloadError as error:
            raise GatewayIngressError(400, str(error)) from error

        source_id = integration.config.get("source_id", "")
        if parsed.source_id != source_id:
            raise GatewayIngressError(409, "Gateway source_id does not match integration")

        message = (
            Message.objects.select_for_update()
            .filter(
                gateway_command_id=parsed.command_id,
                conversation__organization_id=context.organization_id,
                conversation__connection_id=integration.id,
            )
            .first()
        )
        if message is None:
            raise GatewayIngressError(404, "Gateway command not found")
        if message.conversation.external_chat_id != parsed.external_chat_id:
            raise GatewayIngressError(409, "Gateway chat does not match message")

        update_fields: list[str] = []
        if parsed.external_message_id:
            if message.external_id and message.external_id != parsed.external_message_id:
                raise GatewayIngressError(409, "Gateway provider message does not match message")
            if not message.external_id:
                message.external_id = parsed.external_message_id
                update_fields.append("external_id")

        if _should_advance(message.delivery_status, parsed.status):
            message.delivery_status = parsed.status
            message.delivery_status_at = parsed.occurred_at or timezone.now()
            message.delivery_failure_kind = _failure_kind_for(parsed.status)
            update_fields.extend(
                ["delivery_status", "delivery_status_at", "delivery_failure_kind"]
            )

        if update_fields:
            message.save(update_fields=update_fields)

    gateway_authenticated_request(
        integration_id=integration_id,
        authorization=authorization,
        operation=accept,
    )


def _should_advance(current: str, incoming: str) -> bool:
    if current in {DeliveryStatus.UNSET, DeliveryStatus.QUEUED}:
        return True
    if current == incoming:
        return False
    if current == DeliveryStatus.PROVIDER_ACCEPTED:
        return incoming in {
            DeliveryStatus.DELIVERED,
            DeliveryStatus.READ,
            DeliveryStatus.FAILED,
            DeliveryStatus.NO_ACCOUNT,
        }
    if current in {DeliveryStatus.FAILED, DeliveryStatus.NO_ACCOUNT}:
        return incoming in {DeliveryStatus.DELIVERED, DeliveryStatus.READ}
    if current == DeliveryStatus.DELIVERED:
        return incoming == DeliveryStatus.READ
    return False


def _failure_kind_for(status: str) -> str:
    if status == DeliveryStatus.FAILED:
        return "provider_failed"
    if status == DeliveryStatus.NO_ACCOUNT:
        return "no_account"
    return ""
