"""VK native-reply seam for the existing Bots Long Poll.

Stage A/B only observes outgoing events in SHADOW. It must not persist a
second Chatballs Message, claim a native author or supersede an AI turn
until own outbound echoes can be correlated (stage C/D).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from chatballs.native_mirror.policy import MirrorMode, mode_for_config

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


def observe_vk_reply(integration, event: VkNativeReply) -> None:
    """Diagnostic-only hook; fail closed if ENABLED is configured too early."""
    mode = mode_for_config(integration.config)
    if mode == MirrorMode.ENABLED:
        # Stage D installs real persistence. Until then acknowledging ENABLED
        # would silently lose a required native reply when the cursor moves.
        raise RuntimeError("VK native mirror ENABLED before adapter persistence is ready")
    if mode == MirrorMode.SHADOW:
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
