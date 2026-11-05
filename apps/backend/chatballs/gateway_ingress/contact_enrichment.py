"""Optional contact-phone enrichment for authenticated Gateway inbound messages.

Provider-reported numbers are not user-shared contact messages. This adapter
only fills an empty Contact.phone after the normal inbound ingest succeeds.
"""

from __future__ import annotations

import re

from chatballs.conversations.models import ConnectionIdentity, Contact
from chatballs.integrations.models import Integration

_PHONE_PATTERN = re.compile(r"\+?[0-9 ()\-.]+")


def normalize_provider_phone(raw: str) -> str:
    """Normalize usable provider metadata to +E.164; ignore hidden/invalid data."""
    value = raw.strip()
    if not value or not _PHONE_PATTERN.fullmatch(value):
        return ""

    digits = re.sub(r"\D", "", value)
    if len(digits) == 10 and digits.startswith("9"):
        return f"+7{digits}"
    if len(digits) == 11 and digits.startswith("8") and not value.startswith("+"):
        return f"+7{digits[1:]}"
    if 11 <= len(digits) <= 15 and digits[0] != "0":
        return f"+{digits}"
    return ""


def enrich_contact_phone(*, integration: Integration, external_user_id: str, provider_phone: str) -> None:
    """Fill the existing contact only; never verify or merge identities."""
    phone = normalize_provider_phone(provider_phone)
    if not phone:
        return

    contact_id = (
        ConnectionIdentity.objects.filter(
            connection_id=integration.id,
            external_user_id=external_user_id,
            contact__organization_id=integration.organization_id,
        )
        .values_list("contact_id", flat=True)
        .first()
    )
    if contact_id is None:
        return

    # Conditional update is idempotent and does not overwrite manual/contact-share phones.
    Contact.objects.filter(
        id=contact_id,
        organization_id=integration.organization_id,
        merged_into__isnull=True,
        phone="",
    ).update(phone=phone)
