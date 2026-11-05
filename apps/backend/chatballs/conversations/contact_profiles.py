"""Provider-supplied contact profile updates, scoped to an existing identity.

Do not turn a phone observed by a provider into a user-verified phone.
An operator's custom Contact.name/phone wins over later provider snapshots.
"""
from __future__ import annotations

import re

from chatballs.conversations.models import ConnectionIdentity, Contact


def apply_provider_profile(
    identity: ConnectionIdentity, *,
    display_name: str = "", username: str = "", provider_phone: str = "",
) -> list[str]:
    """Apply nonempty provider fields; never erase data missing in a webhook.

    The identity stores the *last provider value*. Comparing it with Contact
    allows automatic values to evolve while protecting manual card edits.
    Caller holds a transaction and has selected/locked the identity.
    """
    contact: Contact = identity.contact
    changes: list[str] = []
    identity_changes: list[str] = []
    name = display_name.strip()
    if name and name.casefold() != "guest":
        previous = identity.display_name
        if name != previous:
            identity.display_name = name
            identity_changes.append("display_name")
        if contact.name != name and (
            not contact.name or contact.name.casefold() == "guest" or contact.name == previous
        ):
            contact.name = name
            changes.append("name")
    if username and username != identity.username:
        identity.username = username
        identity_changes.append("username")
    if provider_phone and re.fullmatch(r"\+?[0-9]{7,15}", provider_phone):
        previous_phone = identity.provider_phone
        if provider_phone != previous_phone:
            identity.provider_phone = provider_phone
            identity_changes.append("provider_phone")
            if not contact.phone or contact.phone == previous_phone:
                contact.phone = provider_phone
                changes.append("phone")
    if identity_changes:
        identity.save(update_fields=identity_changes)
    if changes:
        contact.save(update_fields=changes)
    return changes
