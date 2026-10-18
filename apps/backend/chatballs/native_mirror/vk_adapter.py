"""VK native-reply seam for the existing Bots Long Poll.

Routes message_reply to the existing transactional native mirror.
No VK administrator identity lookup or second Long Poll.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from chatballs.i18n import customer_language, t
from chatballs.integrations.models import IntegrationProvider
from chatballs.native_mirror.classification import OriginClass
from chatballs.native_mirror.contracts import NativeReplyEvent
from chatballs.native_mirror.policy import MirrorMode, mode_for_config
from chatballs.native_mirror.service import accept_native_reply

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VkNativeReply:
    peer_id: str
    message_id: str
    text: str
    occurred_at: int | None = None
    conversation_message_id: str = ""
    has_attachments: bool = False


def parse_vk_reply(update: dict) -> VkNativeReply:
    """Accept both object.message and older flat object event shapes."""
    payload = update.get("object") or {}
    message = payload.get("message") or payload
    message_id = message.get("id")
    if message_id in (None, "", 0, "0"):
        message_id = message.get("conversation_message_id")
    peer_id = message.get("peer_id")
    date = message.get("date")
    return VkNativeReply(
        peer_id=str(peer_id) if peer_id is not None else "",
        message_id=str(message_id) if message_id is not None else "",
        text=str(message.get("text") or ""),
        occurred_at=date if type(date) is int and date > 0 else None,
        conversation_message_id=str(message.get("conversation_message_id") or ""),
        has_attachments=bool(message.get("attachments")),
    )


def observe_vk_reply(integration, event: VkNativeReply, *, context=None) -> None:
    """Forward enabled native replies into our existing receipt/revision core."""
    mode = mode_for_config(integration.config)
    if mode == MirrorMode.ENABLED:
        if context is None:
            raise RuntimeError("VK Native requires a tenant context")
        if not event.peer_id or not event.message_id:
            raise ValueError("VK native reply missing provider identifiers")
        source_id = str(integration.config.get("bot_id") or "")
        if not source_id:
            raise ValueError("VK native reply missing verified community bot_id")
        body = event.text
        if not body.strip() and event.has_attachments:
            body = t(
                "conversations.attachment_unsupported",
                language=customer_language(integration.organization),
            )
        if not body.strip():
            return
        normalized = NativeReplyEvent(
            integration_id=integration.id,
            provider=IntegrationProvider.VK,
            source_id=source_id,
            external_chat_id=event.peer_id,
            event_id=f"vk-reply:{event.peer_id}:{event.message_id}",
            external_message_id=event.message_id,
            occurred_at=datetime.fromtimestamp(event.occurred_at or 0, tz=UTC),
            text=body,
        )
        # The Long Poll connection authenticates the community, not a named
        # administrator. The core supplies the technical VK Native label.
        accept_native_reply(
            event=normalized, context=context,
            origin=OriginClass.EXTERNAL_AUTHORIZED,
        )
    elif mode == MirrorMode.SHADOW:
        logger.info(
            "VK native mirror SHADOW integration=%s has_peer=%s has_id=%s "
            "has_date=%s has_text=%s has_attachments=%s",
            integration.id,
            bool(event.peer_id),
            bool(event.message_id),
            event.occurred_at is not None,
            bool(event.text),
            event.has_attachments,
        )
