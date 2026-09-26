from __future__ import annotations

import hashlib
import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    ExpectedResponder,
    LifecycleState,
    Message,
    MessageAuthor,
)
from chatballs.events.models import EventOwnership, InboxEvent
from chatballs.identity.models import OrganizationMembership

from .payloads import (
    GatewayPayloadError,
    UnsupportedGatewayChatError,
    parse_operator_mirror_payload,
)
from .security import GatewayIngressError
from .services import gateway_authenticated_request

logger = logging.getLogger(__name__)


def accept_gateway_operator_mirror(
    *, integration_id: int, authorization: str, payload: object
) -> None:
    def accept(context, integration) -> None:
        try:
            parsed = parse_operator_mirror_payload(payload)
        except UnsupportedGatewayChatError as error:
            raise GatewayIngressError(422, str(error)) from error
        except GatewayPayloadError as error:
            raise GatewayIngressError(400, str(error)) from error

        if parsed.source_id != integration.config.get("source_id", ""):
            raise GatewayIngressError(409, "Gateway source_id does not match integration")

        native_user_id = integration.config.get("native_operator_user_id")
        if isinstance(native_user_id, bool) or not isinstance(native_user_id, int):
            raise GatewayIngressError(409, "Gateway native operator is not configured")
        membership = (
            OrganizationMembership.objects.select_related("user")
            .filter(user_id=native_user_id, organization_id=context.organization_id)
            .first()
        )
        if membership is None:
            raise GatewayIngressError(409, "Gateway native operator is not configured")
        native_user = membership.user

        try:
            with transaction.atomic():
                InboxEvent.objects.create(
                    source=f"gateway-operator:{integration.id}",
                    external_event_id=parsed.event_id,
                    payload_hash=hashlib.sha256(parsed.text.encode("utf-8")).hexdigest()[:32],
                    ownership=EventOwnership.TENANT,
                    organization=context.organization,
                )
        except IntegrityError:
            return

        matches = list(
            Conversation.objects.select_for_update(of=("self",))
            .filter(
                organization_id=context.organization_id,
                connection=integration,
                external_chat_id=parsed.external_chat_id,
                lifecycle=LifecycleState.OPEN,
            )
            .order_by("id")[:2]
        )
        if len(matches) != 1:
            logger.warning(
                "Gateway operator mirror skipped: conversation match count=%s integration=%s chat=%s event=%s",
                len(matches),
                integration.id,
                parsed.external_chat_id,
                parsed.event_id,
            )
            return

        conversation = matches[0]
        Message.objects.create(
            conversation=conversation,
            author_type=MessageAuthor.OPERATOR,
            author_user=native_user,
            external_id=parsed.external_message_id,
            external_occurred_at=parsed.occurred_at,
            external_reply_to_id=parsed.reply_to_message_id,
            text=parsed.text,
        )
        conversation.control_mode = ControlMode.HUMAN
        conversation.expected_responder = ExpectedResponder.CUSTOMER
        conversation.waiting_since = None
        conversation.last_activity_at = timezone.now()
        conversation.save(
            update_fields=[
                "control_mode",
                "expected_responder",
                "waiting_since",
                "last_activity_at",
            ]
        )

    gateway_authenticated_request(
        integration_id=integration_id,
        authorization=authorization,
        operation=accept,
    )
